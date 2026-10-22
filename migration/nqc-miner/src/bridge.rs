//! Export-only contract. No connection, subscription, or observer writer exists.
use crate::{
    config::{DataClass, NAMESPACE, PRODUCER},
    digest, valid_identifier,
};
use serde::Serialize;
use serde_json::Value;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum BridgeError {
    #[error("observer integration is disabled for the isolated Miner build")]
    Disabled,
    #[error("invalid export identity")]
    Identity,
    #[error("export encoding: {0}")]
    Encoding(#[from] serde_json::Error),
}

#[derive(Debug, Clone, Serialize)]
pub struct ExportEnvelope {
    schema: String,
    producer: String,
    namespace: String,
    run_id: String,
    data_class: DataClass,
    artifact_sha256: String,
    payload: Value,
    grants_execution_authority: bool,
}

impl ExportEnvelope {
    pub fn research_only(
        run_id: &str,
        class: DataClass,
        payload: Value,
    ) -> Result<Self, BridgeError> {
        if !valid_identifier(run_id) {
            return Err(BridgeError::Identity);
        }
        Ok(Self {
            schema: "nqc-miner-export-v1".into(),
            producer: PRODUCER.into(),
            namespace: NAMESPACE.into(),
            run_id: run_id.into(),
            data_class: class,
            artifact_sha256: digest(&serde_json::to_vec(&payload)?),
            payload,
            grants_execution_authority: false,
        })
    }

    /// An artifact can be reviewed locally. It can never enable execution here.
    pub fn deliver_to_observer(&self) -> Result<(), BridgeError> {
        Err(BridgeError::Disabled)
    }
}
