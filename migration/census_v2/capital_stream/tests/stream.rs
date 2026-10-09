use nqc_capital_stream_readback::{relevant, scan, Expected};
use nqc_census_capital::artifacts::parse_capital_sources_artifact;
use nqc_census_chain::json::Json;
use sha2::{Digest, Sha256};
use std::io::Cursor;

type Result = std::result::Result<(), Box<dyn std::error::Error>>;
const AAVE: &[u8] = include_bytes!("fixtures/aave-source.jsonl");
const V2: &[u8] = include_bytes!("fixtures/v2-source.jsonl");

fn check(
    bytes: &[u8],
    rows: u64,
) -> std::result::Result<nqc_capital_stream_readback::Scan, Box<dyn std::error::Error>> {
    let source = parse_capital_sources_artifact(AAVE)?;
    let aave = &source[0];
    let doc = Json::parse(AAVE)?;
    let digest = format!("{:x}", Sha256::digest(bytes));
    let expected = Expected {
        sha256: &digest,
        bytes: bytes.len() as u64,
        rows,
        code_commit: doc.str_field("code_commit")?,
        code_tree: doc.str_field("code_tree")?,
        anchor: aave.anchor(),
        pool: aave.source_contract().ok_or("fixture has no pool")?,
    };
    scan(Cursor::new(bytes), &expected)
}

#[test]
fn real_record_stream_matches_existing_decoder_and_provider_selection() -> Result {
    let mut bytes = V2.to_vec();
    bytes.extend_from_slice(AAVE);
    let result = check(&bytes, 2)?;
    let all = parse_capital_sources_artifact(&bytes)?;
    let source = parse_capital_sources_artifact(AAVE)?;
    let aave = &source[0];
    let e = Expected {
        sha256: "unused",
        bytes: 0,
        rows: 0,
        code_commit: "unused",
        code_tree: "unused",
        anchor: aave.anchor(),
        pool: aave.source_contract().ok_or("no pool")?,
    };
    assert_eq!(result.rows, all.len() as u64);
    assert_eq!(
        result.selected_rows,
        all.iter().filter(|s| relevant(s, &e)).count() as u64
    );
    assert_eq!(result.selected_rows, 1);
    assert_eq!(result.selected_bytes, AAVE);
    assert_eq!(result.selected_blocked, 1);
    Ok(())
}

#[test]
fn selected_view_is_order_independent_but_full_digest_is_not() -> Result {
    let mut left = V2.to_vec();
    left.extend_from_slice(AAVE);
    let mut right = AAVE.to_vec();
    right.extend_from_slice(V2);
    let l = check(&left, 2)?;
    let r = check(&right, 2)?;
    assert_eq!(l.selected_bytes, r.selected_bytes);
    assert_ne!(l.sha256, r.sha256);
    Ok(())
}

#[test]
fn duplicate_selected_and_unselected_records_are_rejected() {
    for row in [AAVE, V2] {
        let mut bytes = row.to_vec();
        bytes.extend_from_slice(row);
        assert!(check(&bytes, 2).is_err());
    }
}

#[test]
fn malformed_tail_cannot_hide_behind_valid_first_record() {
    let mut bad = AAVE.to_vec();
    bad.extend_from_slice(b"{\"source_id\":\"fake\"}\n");
    assert!(check(&bad, 2).is_err());
    assert!(check(&AAVE[..AAVE.len() - 1], 1).is_err());
    let mut blank = AAVE.to_vec();
    blank.push(b'\n');
    assert!(check(&blank, 2).is_err());
}

#[test]
fn oversized_rows_and_missing_population_fail_closed() {
    assert!(check(&[b'x'; 65538], 1).is_err());
    assert!(check(AAVE, 2).is_err());
    assert!(check(AAVE, 0).is_err());
}

#[test]
fn wrong_digest_and_provenance_and_anchor_fail_closed() -> Result {
    let sources = parse_capital_sources_artifact(AAVE)?;
    let s = &sources[0];
    let doc = Json::parse(AAVE)?;
    let digest = format!("{:x}", Sha256::digest(AAVE));
    let mut expected = Expected {
        sha256: &digest,
        bytes: AAVE.len() as u64,
        rows: 1,
        code_commit: doc.str_field("code_commit")?,
        code_tree: doc.str_field("code_tree")?,
        anchor: s.anchor(),
        pool: s.source_contract().ok_or("no pool")?,
    };
    expected.sha256 = "00";
    assert!(scan(Cursor::new(AAVE), &expected).is_err());
    expected.sha256 = &digest;
    expected.code_commit = "different";
    assert!(scan(Cursor::new(AAVE), &expected).is_err());
    expected.code_commit = doc.str_field("code_commit")?;
    expected.code_tree = "different";
    assert!(scan(Cursor::new(AAVE), &expected).is_err());
    expected.code_tree = doc.str_field("code_tree")?;
    let a = s.anchor();
    let wrong = nqc_census_core::StateAnchor::new(
        a.chain().clone(),
        a.block_number() + 1,
        a.block_hash(),
        a.parent_hash(),
        a.timestamp(),
        a.state_root(),
    )?;
    expected.anchor = &wrong;
    assert!(scan(Cursor::new(AAVE), &expected).is_err());
    Ok(())
}
