use nqc_capital_stream_readback::{scan, Expected};
use nqc_census_chain::json::Json;
use nqc_census_core::{Address, ChainDomain, Hash32, StateAnchor};
use std::{
    env,
    error::Error,
    fs::{self, File, OpenOptions},
    io::{BufReader, Write},
    path::PathBuf,
};

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 2 {
        return Err(
            "usage: nqc-capital-stream-readback <exact-capital-sources.jsonl> <new-output-dir>"
                .into(),
        );
    }
    let out = PathBuf::from(&args[1]);
    if out.exists() {
        return Err("output directory already exists".into());
    }
    let anchor = StateAnchor::new(
        ChainDomain::new(
            1,
            Hash32::parse_hex(
                "0xd4e56740f876aef8c010b86a40d5f56745a118d0906a34e69aec8c0db1cb8fa3",
            )?,
            Hash32::parse_hex(
                "0x349462d471690c164b8109c6dbc41a76afb4033216f379254b3367b75f0fc522",
            )?,
        )?,
        26095351,
        Hash32::parse_hex("0x0d7a15fbb72e69696a33c65bc20902fe08e5630862ada64b065a97405c70c781")?,
        Hash32::parse_hex("0xaf6809f0222903662e0814128c37e98296d47c2a78c4d94bdc08e3efa1107792")?,
        1790832215,
        Hash32::parse_hex("0x295ca34af4c1652ded4210d6353703c7acea726c04c27978df4a3a88d9e7bbfd")?,
    )?;
    let expected = Expected {
        sha256: "b97cf0d8cb1dfcaaae7f2b79a3eef40e20b7cd9d7a7c996ab15960153adefb48",
        bytes: 3757728513,
        rows: 1045459,
        code_commit: "83395dc182cb7fd31293887f4de86fcd022b4b6d",
        code_tree: "1ab7d599776babd5aeb3478d44c3c692fb9ad5d8",
        anchor: &anchor,
        pool: Address::parse_hex("0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2")?,
    };
    let file = File::open(&args[0])?;
    if file.metadata()?.len() != expected.bytes {
        return Err("wrong pinned source file size".into());
    }
    let result = scan(BufReader::new(file), &expected)?;
    let report = Json::object([
        (
            "schema",
            Json::string("nqc-full-capital-stream-readback-v1"),
        ),
        (
            "status",
            Json::string("FULL_CANONICAL_SOURCE_STREAM_VERIFIED_DERIVED_AAVE_VIEW"),
        ),
        ("source_bytes", Json::uint(result.bytes)),
        ("source_rows", Json::uint(result.rows)),
        ("source_sha256", Json::string(&result.sha256)),
        ("source_code_commit", Json::string(expected.code_commit)),
        ("source_code_tree", Json::string(expected.code_tree)),
        ("selected_rows", Json::uint(result.selected_rows)),
        (
            "selected_execution_blocked",
            Json::uint(result.selected_blocked),
        ),
        ("selected_sha256", Json::string(&result.selected_sha256)),
        (
            "excluded_rows",
            Json::uint(result.rows - result.selected_rows),
        ),
        ("selected_view_replaces_full_universe", Json::Bool(false)),
        ("upstream_state_import_reexecuted", Json::Bool(false)),
        ("canonical_recertification", Json::Bool(false)),
        ("capital_policy_v2_financing_proven", Json::Bool(false)),
        ("real_market_census_closed", Json::Bool(false)),
    ])
    .canonical()?;
    fs::create_dir(&out)?;
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(out.join("capital-sources-aave-view.jsonl"))?
        .write_all(&result.selected_bytes)?;
    let mut f = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(out.join("stream-readback.json"))?;
    f.write_all(&report)?;
    f.write_all(b"\n")?;
    println!(
        "CANONICAL_SOURCE_STREAM_PASS rows={} selected={} blocked={}",
        result.rows, result.selected_rows, result.selected_blocked
    );
    Ok(())
}
