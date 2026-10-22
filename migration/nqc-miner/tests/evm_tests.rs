use alloy_primitives::keccak256;
use nqc_miner::discovery::decode_hex;
use nqc_miner::evm::*;
use proptest::prelude::*;
use std::collections::BTreeMap;

fn a(b: u8) -> String {
    format!("0x{}", format!("{b:02x}").repeat(20))
}
fn h(b: u8) -> String {
    format!("0x{}", format!("{b:02x}").repeat(32))
}
fn account(b: u8, code: &str) -> WitnessAccount {
    WitnessAccount {
        address: a(b),
        exists: true,
        balance_wei: "1000000000000000000".into(),
        nonce: 0,
        runtime_code: code.into(),
        code_hash: format!("{:#x}", keccak256(decode_hex(code).unwrap())),
        storage: BTreeMap::new(),
    }
}
fn snapshot(code: &str) -> PinnedSnapshot {
    PinnedSnapshot {
        schema_version: 1,
        kind: SnapshotKind::SyntheticFixture,
        chain_id: 1,
        block_number: 100,
        block_hash: h(1),
        state_root: h(2),
        timestamp: 1000,
        fork: EvmFork::Shanghai,
        block_gas_limit: 30_000_000,
        base_fee_wei: "1".into(),
        beneficiary: a(3),
        prevrandao: h(4),
        excess_blob_gas: None,
        accounts: vec![account(1, "0x"), account(2, code), account(3, "0x")],
        ancestor_block_hashes: BTreeMap::new(),
    }
}
fn call() -> SandboxCall {
    SandboxCall {
        caller: a(1),
        to: a(2),
        calldata: "0x".into(),
        value_wei: "0".into(),
        gas_limit: 100_000,
        gas_price_wei: "1".into(),
        nonce: 0,
    }
}

#[test]
fn real_revm_executes_return_value_and_is_deterministic() {
    // PUSH1 42 PUSH1 0 MSTORE PUSH1 32 PUSH1 0 RETURN.
    let snapshot = snapshot("0x602a60005260206000f3");
    let call = call();
    let first = simulate(&snapshot, &call).unwrap();
    let second = simulate(&snapshot, &call).unwrap();
    assert_eq!(first, second);
    assert_eq!(first.status, VmStatus::Success);
    assert_eq!(first.output, format!("0x{:064x}", 42));
    assert!(!first.canonical_state_authenticated);
    assert_eq!(first.snapshot_kind, SnapshotKind::SyntheticFixture);
    assert!(first.gas_used > 21_000 && first.gas_used < 100_000);
    assert_eq!(snapshot.accounts[0].nonce, 0); // supplied snapshot never mutates.
}

#[test]
fn missing_storage_is_an_error_and_explicit_zero_is_valid() {
    let mut snapshot = snapshot("0x60005460005260206000f3");
    let err = simulate(&snapshot, &call()).unwrap_err();
    assert!(err.0.contains("missing storage witness"));
    snapshot.accounts[1].storage.insert("0".into(), "0".into());
    let result = simulate(&snapshot, &call()).unwrap();
    assert_eq!(result.output, h(0));
    snapshot.accounts[1]
        .storage
        .insert("0".into(), "123".into());
    assert_eq!(
        simulate(&snapshot, &call()).unwrap().output,
        format!("0x{:064x}", 123)
    );
}

#[test]
fn missing_accounts_cannot_be_defaulted_to_empty() {
    // PUSH20 absent_address BALANCE then return.
    let code = format!("0x73{}3160005260206000f3", &a(9)[2..]);
    let mut snapshot = snapshot(&code);
    assert!(simulate(&snapshot, &call())
        .unwrap_err()
        .0
        .contains("missing account witness"));
    let mut absent = account(9, "0x");
    absent.exists = false;
    absent.balance_wei = "0".into();
    snapshot.accounts.push(absent);
    assert_eq!(simulate(&snapshot, &call()).unwrap().output, h(0));
}

#[test]
fn ancestor_hash_reads_require_explicit_witness() {
    let mut snapshot = snapshot("0x60634060005260206000f3");
    assert!(simulate(&snapshot, &call())
        .unwrap_err()
        .0
        .contains("missing ancestor block hash"));
    snapshot.ancestor_block_hashes.insert(99, h(7));
    assert_eq!(simulate(&snapshot, &call()).unwrap().output, h(7));
    snapshot.ancestor_block_hashes.insert(100, h(8));
    assert!(simulate(&snapshot, &call()).is_err());
}

#[test]
fn duplicate_inconsistent_or_incomplete_witnesses_fail() {
    let mut s = snapshot("0x00");
    s.accounts[1].code_hash = h(8);
    assert!(simulate(&s, &call()).is_err());
    s = snapshot("0x00");
    s.accounts.push(s.accounts[1].clone());
    assert!(simulate(&s, &call()).is_err());
    s = snapshot("0x00");
    s.accounts[1].exists = false;
    assert!(simulate(&s, &call()).is_err());
    s = snapshot("0x00");
    s.accounts[1].storage.insert("0".into(), "1".into());
    s.accounts[1].storage.insert("0x0".into(), "2".into());
    assert!(simulate(&s, &call()).is_err());
    s = snapshot("0x00");
    s.fork = EvmFork::Cancun;
    assert!(simulate(&s, &call()).is_err());
    s.excess_blob_gas = Some(0);
    assert!(simulate(&s, &call()).is_ok());
}

#[test]
fn revert_halt_and_resource_bounds_are_explicit() {
    assert_eq!(
        simulate(&snapshot("0x60006000fd"), &call()).unwrap().status,
        VmStatus::Revert
    );
    assert_eq!(
        simulate(&snapshot("0xfe"), &call()).unwrap().status,
        VmStatus::Halt
    );
    let mut call = call();
    call.gas_limit = 30_000_001;
    assert!(simulate(&snapshot("0x00"), &call).is_err());
    call.gas_limit = 20_999;
    assert!(simulate(&snapshot("0x00"), &call).is_err());
    call.gas_limit = 100_000;
    call.nonce = 1;
    assert!(simulate(&snapshot("0x00"), &call).is_err());
}

#[test]
fn malformed_eof_and_future_delegation_never_panic_or_silently_use_newer_rules() {
    assert!(simulate(&snapshot("0xef00"), &call()).is_err());
    assert!(simulate(&snapshot("0xef01"), &call()).is_err());
    assert!(simulate(&snapshot(&format!("0xef0100{}", &a(9)[2..])), &call()).is_err());
}

#[test]
fn differential_harness_detects_values_state_gas_and_input_mismatch() {
    let actual = simulate(&snapshot("0x602a60005260206000f3"), &call()).unwrap();
    let mut predicted = actual.clone();
    predicted.output = h(9);
    predicted.gas_used += 1;
    predicted.account_deltas[0].nonce += 1;
    let diff = compare_adapter_output(&actual, &predicted).unwrap();
    assert!(!diff.matches);
    assert!(diff.mismatches.contains(&"output".into()));
    assert!(diff.mismatches.contains(&"gas_used".into()));
    assert!(diff.mismatches.contains(&"state_delta".into()));
    assert!(!diff.establishes_adapter_certification);
    predicted = actual.clone();
    predicted.snapshot_sha256 = h(8);
    assert!(compare_adapter_output(&actual, &predicted).is_err());
}

fn sample_probe() -> TransferProbe {
    let snapshot = snapshot("0x600160005260206000f3");
    let mut call = call();
    call.calldata = format!("0xa9059cbb{}{}{:064x}", "00".repeat(12), &a(4)[2..], 10);
    let outcome = simulate(&snapshot, &call).unwrap();
    TransferProbe {
        token: a(2),
        sender: a(1),
        receiver: a(4),
        amount: "10".into(),
        sender_before: "100".into(),
        sender_after: "90".into(),
        receiver_before: "0".into(),
        receiver_after: "10".into(),
        call,
        outcome,
    }
}

#[test]
fn missing_toxicity_evidence_never_means_safe() {
    let probe = sample_probe();
    let digest = probe.outcome.snapshot_sha256.clone();
    let result = assess_toxicity(&digest, &[], None).unwrap();
    assert_eq!(result.verdict, ToxicityVerdict::Unknown);
    let result = assess_toxicity(&digest, std::slice::from_ref(&probe), None).unwrap();
    assert_eq!(result.verdict, ToxicityVerdict::Unknown);
    assert!(!result.globally_safe);
    let oracle = OracleStressEvidence {
        snapshot_sha256: digest.clone(),
        liquidity_evidence_sha256: h(9),
        manipulation_cost_microusd: Some(1000),
        maximum_extractable_microusd: Some(100),
        all_dependency_paths_evaluated: false,
    };
    assert_eq!(
        assess_toxicity(&digest, &[probe], Some(&oracle))
            .unwrap()
            .verdict,
        ToxicityVerdict::Unknown
    );
}

#[test]
fn hidden_transfer_fees_and_cheap_oracle_manipulation_are_rejected() {
    let mut probe = sample_probe();
    let digest = probe.outcome.snapshot_sha256.clone();
    probe.receiver_after = "9".into();
    assert_eq!(
        assess_toxicity(&digest, &[probe.clone()], None)
            .unwrap()
            .verdict,
        ToxicityVerdict::Rejected
    );
    probe.receiver_after = "10".into();
    let mut oracle = OracleStressEvidence {
        snapshot_sha256: digest.clone(),
        liquidity_evidence_sha256: h(9),
        manipulation_cost_microusd: Some(100),
        maximum_extractable_microusd: Some(100),
        all_dependency_paths_evaluated: true,
    };
    assert_eq!(
        assess_toxicity(&digest, &[probe.clone()], Some(&oracle))
            .unwrap()
            .verdict,
        ToxicityVerdict::Rejected
    );
    oracle.manipulation_cost_microusd = Some(101);
    let result = assess_toxicity(&digest, &[probe], Some(&oracle)).unwrap();
    assert_eq!(result.verdict, ToxicityVerdict::PassForSuppliedCases);
    assert!(!result.globally_safe);
}

#[test]
fn transfer_result_cannot_be_relabelled_as_a_different_actor_or_amount() {
    let mut probe = sample_probe();
    let digest = probe.outcome.snapshot_sha256.clone();
    probe.amount = "11".into();
    assert!(assess_toxicity(&digest, &[probe], None).is_err());
    let mut probe = sample_probe();
    probe.sender = a(5);
    assert!(assess_toxicity(&digest, &[probe], None).is_err());
    let mut probe = sample_probe();
    probe.outcome.call_sha256 = h(8);
    assert!(assess_toxicity(&digest, &[probe], None).is_err());
}

proptest! {
    #[test]
    fn arbitrary_short_bytecode_fails_or_halts_without_fetching(code in prop::collection::vec(any::<u8>(),0..48)){
        let mut encoded=String::from("0x");for b in code{encoded.push_str(&format!("{b:02x}"));}
        let s=snapshot(&encoded);let mut c=call();c.gas_limit=30_000;
        if let Ok(result)=simulate(&s,&c){prop_assert!(result.gas_used<=30_000);prop_assert!(!result.canonical_state_authenticated);}
    }
}
