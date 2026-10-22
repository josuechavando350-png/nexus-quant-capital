use clap::{Parser, Subcommand};
use nqc_miner::{analytics, config::MinerConfig, discovery, evm, ingestion, journal, reporting};
use serde::Deserialize;
use serde_json::json;
use std::{
    error::Error,
    io::Read,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Parser)]
#[command(
    name = "nqc-miner",
    version,
    about = "Isolated NQC discovery and research. No signing or transaction submission."
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Show exact build identity and enforced isolation settings.
    About,
    /// Supported canonical event signatures and protocol families.
    Topics,
    /// Validate configuration without connecting to anything.
    ValidateConfig {
        #[arg(long)]
        config: PathBuf,
    },
    /// Finite, read-only, finalized scan. Endpoints are read only from Miner env vars.
    Scan {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        state: PathBuf,
    },
    /// Reconstruct metrics using only this run's local journal.
    Report {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        state: PathBuf,
        #[arg(long)]
        watches: Option<PathBuf>,
        #[arg(long)]
        prometheus: bool,
    },
    /// Verify sequence, event identities, reorg invalidations and all hashes.
    VerifyJournal {
        #[arg(long)]
        state: PathBuf,
    },
    /// Decode one scoped ABI log. Output remains an uncertified candidate.
    Decode {
        #[arg(long)]
        input: PathBuf,
    },
    /// Seeded conditional Monte Carlo from explicitly labeled daily observations.
    Value {
        #[arg(long)]
        input: PathBuf,
    },
    /// Execute only a supplied closed state snapshot in local REVM.
    Simulate {
        #[arg(long)]
        input: PathBuf,
    },
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DecodeInput {
    scope: discovery::ContractScope,
    log: discovery::RpcLog,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ValueInput {
    history: Vec<analytics::DailyEconomics>,
    config: analytics::ValuationConfig,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SimulationInput {
    snapshot: evm::PinnedSnapshot,
    call: evm::SandboxCall,
}

fn read_json<T: serde::de::DeserializeOwned>(path: &Path) -> Result<T, Box<dyn Error>> {
    let file = std::fs::File::open(path)?;
    let mut bytes = Vec::new();
    file.take(32 * 1024 * 1024 + 1).read_to_end(&mut bytes)?;
    if bytes.len() > 32 * 1024 * 1024 {
        return Err("input exceeds 32 MiB limit".into());
    }
    Ok(serde_json::from_slice(&bytes)?)
}
fn print_json(value: &impl serde::Serialize) -> Result<(), Box<dyn Error>> {
    println!("{}", serde_json::to_string_pretty(value)?);
    Ok(())
}

fn run(cli: Cli) -> Result<(), Box<dyn Error>> {
    match cli.command {
        Command::About => print_json(
            &json!({"name":"nqc-miner","version":env!("CARGO_PKG_VERSION"),
            "code_commit":env!("NQC_MINER_BUILD_COMMIT"),"source_dirty":env!("NQC_MINER_BUILD_DIRTY")=="true",
            "source_sha256":env!("NQC_MINER_BUILD_SOURCE_SHA256"),"cargo_lock_sha256":env!("NQC_MINER_BUILD_LOCK_SHA256"),
            "namespace":"nqc_miner_v1","observer_bridge_enabled":false,"signing_enabled":false,
            "gas_budget_mxn_centavos":0,"status":"preparatory-research-build","economic_certification":false}),
        ),
        Command::Topics => print_json(&json!({
            "morpho-blue":discovery::event_topics(discovery::ProtocolFamily::MorphoBlue),
            "aave-v3":discovery::event_topics(discovery::ProtocolFamily::AaveV3Pool),
            "aave-v3-configurator":discovery::event_topics(discovery::ProtocolFamily::AaveV3Configurator)})),
        Command::ValidateConfig { config } => {
            let config = MinerConfig::load(&config)?;
            print_json(
                &json!({"valid":true,"config_sha256":config.integrity_hash()?,"run_id":config.run_id,
                "data_class":config.data_class,"scopes":config.scopes.len(),"network_used":false}),
            )
        }
        Command::Scan { config, state } => {
            let config = MinerConfig::load(&config)?;
            ingestion::validate_runtime(&config)?;
            if env!("NQC_MINER_BUILD_DIRTY") != "false"
                || config.code_commit != env!("NQC_MINER_BUILD_COMMIT")
                || config.cargo_lock_sha256 != env!("NQC_MINER_BUILD_LOCK_SHA256")
            {
                return Err("live read-only evidence requires a clean committed build and matching code/lock identity; run about".into());
            }
            let mut journal = journal::Journal::open(&state, &config)?;
            let mut reports = Vec::new();
            for scope in &config.scopes {
                let quorum = ingestion::QuorumRpc::from_scope(scope)?;
                let observed_at = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
                reports.push(ingestion::scan_scope(
                    scope,
                    &quorum,
                    &mut journal,
                    observed_at,
                )?);
            }
            print_json(&json!({"scans":reports,"journal":journal.summary()}))
        }
        Command::Report {
            config,
            state,
            watches,
            prometheus,
        } => {
            let config = MinerConfig::load(&config)?;
            let watches: Vec<analytics::WatchInterval> = match watches {
                Some(path) => read_json(&path)?,
                None => Vec::new(),
            };
            let report = reporting::report(&config, &state, &watches)?;
            if prometheus {
                print!("{}", reporting::prometheus(&report));
                Ok(())
            } else {
                print_json(&report)
            }
        }
        Command::VerifyJournal { state } => print_json(&journal::verify(&state)?),
        Command::Decode { input } => {
            let value: DecodeInput = read_json(&input)?;
            print_json(&discovery::decode_log(&value.scope, &value.log)?)
        }
        Command::Value { input } => {
            let value: ValueInput = read_json(&input)?;
            print_json(&analytics::value_month(&value.history, &value.config)?)
        }
        Command::Simulate { input } => {
            let value: SimulationInput = read_json(&input)?;
            print_json(&evm::simulate(&value.snapshot, &value.call)?)
        }
    }
}
fn main() {
    if let Err(error) = run(Cli::parse()) {
        eprintln!("nqc-miner: {error}");
        std::process::exit(1);
    }
}
