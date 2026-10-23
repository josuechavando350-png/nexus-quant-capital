//! NQC Miner: isolated research/discovery, with no transaction submission API.
//! Synthetic, historical, shadow and realized evidence have distinct meanings.
#![forbid(unsafe_code)]

pub mod aave_amounts;
pub mod aave_collateral;
pub mod aave_debt;
pub mod aave_reserve;
pub mod aave_validation;
pub mod analytics;
pub mod bridge;
pub mod collector;
pub mod config;
pub mod controls;
pub mod discovery;
pub mod evm;
pub mod historical;
pub mod ingestion;
pub mod journal;
pub mod reporting;

use sha2::{Digest, Sha256};

/// SHA-256 hex digest of exact bytes. This is integrity, not source authentication.
pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub fn valid_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 96
        && value
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-' || b == b'_')
}

pub fn valid_hex(value: &str, bytes: usize) -> bool {
    value.len() == 2 + bytes * 2
        && value.starts_with("0x")
        && value[2..]
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
