use clap::{Parser, Subcommand};
use nqc_miner::{
    analytics, collector, config::MinerConfig, discovery, evm, historical, ingestion, journal,
    reporting,
};
use serde::Deserialize;
use serde_json::json;
use std::{
    error::Error,
    io::Read,
    path::{Path, PathBuf},
    time::{Duration, SystemTime, UNIX_EPOCH},
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
    /// Review supplied Titan gas terms offline; never verifies or authorizes funding.
    AssessGasFunding {
        #[arg(long)]
        input: PathBuf,
    },
    /// Offline debt burn/deficit bookkeeping with explicitly supplied external outcomes.
    CalculateAaveDebt {
        #[arg(long)]
        input: PathBuf,
    },
    /// Offline collateral exhaustion and fee cap; no token transfer is executed.
    CalculateAaveCollateral {
        #[arg(long)]
        input: PathBuf,
    },
    /// Offline reserve update and balances; does not authenticate supplied state.
    ProjectAaveReserve {
        #[arg(long)]
        input: PathBuf,
    },
    /// Offline amount kernel only; supplied balances/prices are not authenticated.
    CalculateAaveAmounts {
        #[arg(long)]
        input: PathBuf,
    },
    /// Offline revision-11 initial conditions only; never certifies execution.
    CheckAaveConditions {
        #[arg(long)]
        input: PathBuf,
    },
    /// Validate historical read bounds and getter scope without network access.
    ValidateAavePlan {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        plan: PathBuf,
    },
    /// Bounded Aave account/oracle reads at exact pre-event block hashes.
    ReadAaveState {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        plan: PathBuf,
    },
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
    /// Rolling historical windows; defaults to one poll. Zero max-polls runs until stopped.
    Follow {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        state: PathBuf,
        #[arg(long, default_value_t = 1)]
        max_polls: u64,
        #[arg(long, default_value_t = 15, value_parser = clap::value_parser!(u64).range(1..=300))]
        poll_seconds: u64,
    },
    /// Offline whole-collection integrity check, including continuity and quarantine.
    VerifyCollector {
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

fn validate_live_build(config: &MinerConfig) -> Result<(), Box<dyn Error>> {
    ingestion::validate_runtime(config)?;
    if env!("NQC_MINER_BUILD_DIRTY") != "false"
        || config.code_commit != env!("NQC_MINER_BUILD_COMMIT")
        || config.cargo_lock_sha256 != env!("NQC_MINER_BUILD_LOCK_SHA256")
        || config.build_identity_sha256.as_deref() != Some(env!("NQC_MINER_BUILD_IDENTITY_SHA256"))
    {
        return Err("live read-only evidence requires a clean committed build and matching code/lock/build identity; run about".into());
    }
    Ok(())
}

fn run(cli: Cli) -> Result<(), Box<dyn Error>> {
    match cli.command {
        Command::AssessGasFunding { input } => {
            let value: nqc_miner::funding::FundingInput = read_json(&input)?;
            print_json(&nqc_miner::funding::assess(&value).map_err(std::io::Error::other)?)
        }
        Command::CalculateAaveDebt { input } => {
            let value: nqc_miner::aave_debt::DebtInput = read_json(&input)?;
            print_json(&nqc_miner::aave_debt::calculate(&value).map_err(std::io::Error::other)?)
        }
        Command::CalculateAaveCollateral { input } => {
            let value: nqc_miner::aave_collateral::CollateralInput = read_json(&input)?;
            print_json(
                &nqc_miner::aave_collateral::calculate(&value).map_err(std::io::Error::other)?,
            )
        }
        Command::ProjectAaveReserve { input } => {
            let value: nqc_miner::aave_reserve::ReserveInput = read_json(&input)?;
            print_json(&nqc_miner::aave_reserve::project(&value).map_err(std::io::Error::other)?)
        }
        Command::CalculateAaveAmounts { input } => {
            let value: nqc_miner::aave_amounts::AmountInput = read_json(&input)?;
            print_json(&nqc_miner::aave_amounts::calculate(&value).map_err(std::io::Error::other)?)
        }
        Command::CheckAaveConditions { input } => {
            let value: nqc_miner::aave_validation::ValidationInput = read_json(&input)?;
            print_json(
                &nqc_miner::aave_validation::validate(&value).map_err(std::io::Error::other)?,
            )
        }
        Command::ValidateAavePlan { config, plan } => {
            let config = MinerConfig::load(&config)?;
            let plan: historical::AaveReadPlan = read_json(&plan)?;
            plan.validate(&config)?;
            print_json(
                &json!({"valid":true,"plan":plan,"network_used":false,"activation_allowed":false}),
            )
        }
        Command::ReadAaveState { config, plan } => {
            let config = MinerConfig::load(&config)?;
            validate_live_build(&config)?;
            let plan: historical::AaveReadPlan = read_json(&plan)?;
            let scope = plan.validate(&config)?;
            let quorum = ingestion::QuorumRpc::from_scope(scope)?;
            print_json(&historical::read_aave(&config, &plan, &quorum)?)
        }
        Command::About => print_json(
            &json!({"name":"nqc-miner","version":env!("CARGO_PKG_VERSION"),
            "code_commit":env!("NQC_MINER_BUILD_COMMIT"),"source_dirty":env!("NQC_MINER_BUILD_DIRTY")=="true",
            "source_sha256":env!("NQC_MINER_BUILD_SOURCE_SHA256"),"cargo_lock_sha256":env!("NQC_MINER_BUILD_LOCK_SHA256"),
            "rustc_version":env!("NQC_MINER_BUILD_RUSTC_VERSION"),"target":env!("NQC_MINER_BUILD_TARGET"),
            "host":env!("NQC_MINER_BUILD_HOST"),"profile":env!("NQC_MINER_BUILD_PROFILE"),
            "opt_level":env!("NQC_MINER_BUILD_OPT_LEVEL"),"debug":env!("NQC_MINER_BUILD_DEBUG")=="true",
            "rustflags_sha256":env!("NQC_MINER_BUILD_RUSTFLAGS_SHA256"),
            "build_identity_sha256":env!("NQC_MINER_BUILD_IDENTITY_SHA256"),
            "namespace":"nqc_miner_v1","observer_bridge_enabled":false,"signing_enabled":false,
            "gas_budget_mxn_centavos":0,"funding_policy":nqc_miner::funding::policy(),
            "status":"preparatory-research-build","economic_certification":false}),
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
            validate_live_build(&config)?;
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
        Command::Follow {
            config,
            state,
            max_polls,
            poll_seconds,
        } => {
            let config = MinerConfig::load(&config)?;
            validate_live_build(&config)?;
            let mut collector = collector::Collector::open(&state, &config)?;
            let mut polls = 0u64;
            let mut quorum = None;
            loop {
                polls = polls.checked_add(1).ok_or("poll counter overflow")?;
                let observed_at = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
                let result = (|| {
                    if quorum.is_none() {
                        quorum = Some(ingestion::QuorumRpc::from_scope(&config.scopes[0])?);
                    }
                    collector.poll(quorum.as_ref().expect("initialized quorum"), observed_at)
                })();
                let last_failed = match result {
                    Ok(outcome) => {
                        println!(
                            "{}",
                            serde_json::to_string(
                                &json!({"poll":polls,"outcome":outcome,"collection":collector.status()?})
                            )?
                        );
                        false
                    }
                    Err(ingestion::IngestError::Provider(_)) => {
                        // Endpoint, response body and credentials are never emitted.
                        println!(
                            "{}",
                            serde_json::to_string(
                                &json!({"poll":polls,"outcome":{"status":"provider_unavailable"},"collection":collector.status()?})
                            )?
                        );
                        true
                    }
                    Err(error) => return Err(error.into()),
                };
                if max_polls != 0 && polls >= max_polls {
                    if last_failed {
                        return Err("last collector poll failed; cursor did not advance for the incomplete window".into());
                    }
                    break;
                }
                std::thread::sleep(Duration::from_secs(poll_seconds));
            }
            Ok(())
        }
        Command::VerifyCollector { config, state } => {
            let config = MinerConfig::load(&config)?;
            if !state.is_dir() {
                return Err("collector state does not exist".into());
            }
            print_json(&collector::Collector::open(&state, &config)?.status()?)
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
