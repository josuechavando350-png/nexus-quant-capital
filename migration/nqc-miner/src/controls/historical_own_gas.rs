//! Superseded MXN budget: historical accounting replay only.
//! Current policy is crate::funding. No spending path is enabled here.
use super::*;
pub const MAX_OWN_GAS_CENTAVOS: u64 = 200_000;
pub const MAX_TOP_UP_CENTAVOS: u64 = 50_000;
pub const NO_CAPTURE_STOP_CENTAVOS: u64 = 100_000;
/// Planning/accounting ceilings only; even a nonzero policy does not authorize spending.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Default)]
pub struct BudgetPolicy {
    total_gas_centavos: u64,
    top_up_centavos: u64,
}
impl BudgetPolicy {
    pub fn new(total_gas_centavos: u64, top_up_centavos: u64) -> Result<Self> {
        if total_gas_centavos > MAX_OWN_GAS_CENTAVOS
            || top_up_centavos > MAX_TOP_UP_CENTAVOS
            || top_up_centavos > total_gas_centavos
            || (total_gas_centavos == 0) != (top_up_centavos == 0)
        {
            return Err(ControlError::BudgetLimit);
        }
        Ok(Self {
            total_gas_centavos,
            top_up_centavos,
        })
    }
    pub fn total_gas_centavos(&self) -> u64 {
        self.total_gas_centavos
    }
    pub fn top_up_centavos(&self) -> u64 {
        self.top_up_centavos
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BudgetHalt {
    NoBudget,
    TopUpLimitBreached,
    BudgetExhausted,
    NoRealizedCapture,
    ReorganizedAccountingEvidence,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PaperResultKind {
    Simulated,
    Shadow,
}

/// A reference to externally verified accounting evidence, not a transaction sender.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct RealizedReceipt {
    chain_id: u64,
    transaction_hash: EvidenceHash,
    canonical_block: CanonicalBlock,
    evidence_hash: EvidenceHash,
}
impl RealizedReceipt {
    pub fn new(
        chain_id: u64,
        transaction_hash: EvidenceHash,
        canonical_block: CanonicalBlock,
        evidence_hash: EvidenceHash,
    ) -> Result<Self> {
        if chain_id == 0 {
            return Err(ControlError::InvalidInput("receipt chain"));
        }
        Ok(Self {
            chain_id,
            transaction_hash,
            canonical_block,
            evidence_hash,
        })
    }
    pub fn evidence_hash(&self) -> EvidenceHash {
        self.evidence_hash
    }
    pub fn transaction_hash(&self) -> EvidenceHash {
        self.transaction_hash
    }
    fn key(&self) -> (u64, EvidenceHash) {
        (self.chain_id, self.transaction_hash)
    }
    fn validate(&self, canonical: &CanonicalView) -> Result<()> {
        canonical.check(self.chain_id, self.canonical_block)
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(tag = "entry_type", rename_all = "snake_case")]
pub enum AccountingRecord {
    Gas {
        centavos: u64,
        receipt: RealizedReceipt,
    },
    Capture {
        net_centavos: u64,
        receipt: RealizedReceipt,
    },
    TopUp {
        centavos: u64,
        receipt: RealizedReceipt,
    },
    Paper {
        kind: PaperResultKind,
        net_centavos: i64,
    },
}
#[derive(Clone, Debug)]
pub struct BudgetLedger {
    policy: BudgetPolicy,
    gas_consumed_centavos: u64,
    observed_top_ups_centavos: u64,
    realized_capture_count: u64,
    realized_net_centavos: u64,
    simulated_net_centavos: i128,
    shadow_net_centavos: i128,
    halt: Option<BudgetHalt>,
    gas_receipts: BTreeSet<(u64, EvidenceHash)>,
    capture_receipts: BTreeSet<(u64, EvidenceHash)>,
    top_up_receipts: BTreeSet<(u64, EvidenceHash)>,
    accounting_records: Vec<AccountingRecord>,
}
impl Default for BudgetLedger {
    fn default() -> Self {
        Self::new(BudgetPolicy::default())
    }
}
impl BudgetLedger {
    pub fn new(policy: BudgetPolicy) -> Self {
        Self {
            policy,
            gas_consumed_centavos: 0,
            observed_top_ups_centavos: 0,
            realized_capture_count: 0,
            realized_net_centavos: 0,
            simulated_net_centavos: 0,
            shadow_net_centavos: 0,
            halt: if policy.total_gas_centavos == 0 {
                Some(BudgetHalt::NoBudget)
            } else {
                None
            },
            gas_receipts: BTreeSet::new(),
            capture_receipts: BTreeSet::new(),
            top_up_receipts: BTreeSet::new(),
            accounting_records: Vec::new(),
        }
    }
    pub fn accounting_records(&self) -> &[AccountingRecord] {
        &self.accounting_records
    }
    /// Recheck receipts from this chain against refreshed canonical evidence; latch on any loss.
    pub fn audit_canonical(&mut self, canonical: &CanonicalView) -> Result<()> {
        for record in &self.accounting_records {
            let receipt = match record {
                AccountingRecord::Gas { receipt, .. }
                | AccountingRecord::Capture { receipt, .. }
                | AccountingRecord::TopUp { receipt, .. } => receipt,
                AccountingRecord::Paper { .. } => continue,
            };
            if receipt.chain_id == canonical.chain_id {
                if let Err(error) = receipt.validate(canonical) {
                    self.halt = Some(BudgetHalt::ReorganizedAccountingEvidence);
                    return Err(error);
                }
            }
        }
        Ok(())
    }
    pub fn gas_consumed_centavos(&self) -> u64 {
        self.gas_consumed_centavos
    }
    pub fn realized_capture_count(&self) -> u64 {
        self.realized_capture_count
    }
    pub fn realized_net_centavos(&self) -> u64 {
        self.realized_net_centavos
    }
    pub fn simulated_net_centavos(&self) -> i128 {
        self.simulated_net_centavos
    }
    pub fn shadow_net_centavos(&self) -> i128 {
        self.shadow_net_centavos
    }
    pub fn halt_reason(&self) -> Option<BudgetHalt> {
        self.halt
    }
    pub fn spending_enabled(&self) -> bool {
        false
    }
    pub fn request_spend(
        &self,
        _centavos: u64,
        _approval: &ExternalApprovalReference,
    ) -> Result<()> {
        Err(ControlError::OperationalBridgeDisabled)
    }
    /// A numerical precheck, never authorization. Actual funding is absent from this build.
    pub fn assess_top_up(&self, centavos: u64) -> Result<()> {
        if self.halt.is_some() {
            return Err(ControlError::BudgetHalted);
        }
        if centavos == 0
            || centavos > self.policy.top_up_centavos
            || self
                .observed_top_ups_centavos
                .checked_add(centavos)
                .ok_or(ControlError::ArithmeticOverflow)?
                > self.policy.total_gas_centavos
        {
            return Err(ControlError::BudgetLimit);
        }
        Ok(())
    }
    pub fn record_paper_result(&mut self, kind: PaperResultKind, net_centavos: i64) -> Result<()> {
        let target = match kind {
            PaperResultKind::Simulated => &mut self.simulated_net_centavos,
            PaperResultKind::Shadow => &mut self.shadow_net_centavos,
        };
        *target = target
            .checked_add(i128::from(net_centavos))
            .ok_or(ControlError::ArithmeticOverflow)?;
        self.accounting_records
            .push(AccountingRecord::Paper { kind, net_centavos });
        Ok(())
    }
    /// Keep observed overspending visible and latch the breach; never discard it as a failed request.
    pub fn record_realized_gas(
        &mut self,
        centavos: u64,
        receipt: &RealizedReceipt,
        canonical: &CanonicalView,
    ) -> Result<()> {
        receipt.validate(canonical)?;
        if centavos == 0 {
            return Err(ControlError::InvalidInput("zero gas accounting entry"));
        }
        if self.gas_receipts.contains(&receipt.key()) {
            return Err(ControlError::DuplicateReceipt);
        }
        let next = self
            .gas_consumed_centavos
            .checked_add(centavos)
            .ok_or(ControlError::ArithmeticOverflow)?;
        self.gas_receipts.insert(receipt.key());
        self.gas_consumed_centavos = next;
        self.accounting_records.push(AccountingRecord::Gas {
            centavos,
            receipt: receipt.clone(),
        });
        self.refresh_halt();
        Ok(())
    }
    pub fn record_realized_capture(
        &mut self,
        net_centavos: u64,
        receipt: &RealizedReceipt,
        canonical: &CanonicalView,
    ) -> Result<()> {
        receipt.validate(canonical)?;
        if net_centavos == 0 {
            return Err(ControlError::InvalidInput(
                "realized net capture must be positive",
            ));
        }
        if self.capture_receipts.contains(&receipt.key()) {
            return Err(ControlError::DuplicateReceipt);
        }
        let next_net = self
            .realized_net_centavos
            .checked_add(net_centavos)
            .ok_or(ControlError::ArithmeticOverflow)?;
        let next_count = self
            .realized_capture_count
            .checked_add(1)
            .ok_or(ControlError::ArithmeticOverflow)?;
        self.capture_receipts.insert(receipt.key());
        self.realized_net_centavos = next_net;
        self.realized_capture_count = next_count;
        self.accounting_records.push(AccountingRecord::Capture {
            net_centavos,
            receipt: receipt.clone(),
        });
        // A later capture never clears a review-required stop already reached.
        self.refresh_halt();
        Ok(())
    }
    pub fn record_observed_top_up(
        &mut self,
        centavos: u64,
        receipt: &RealizedReceipt,
        canonical: &CanonicalView,
    ) -> Result<()> {
        receipt.validate(canonical)?;
        if centavos == 0 {
            return Err(ControlError::InvalidInput("zero top-up accounting entry"));
        }
        if self.top_up_receipts.contains(&receipt.key()) {
            return Err(ControlError::DuplicateReceipt);
        }
        let next = self
            .observed_top_ups_centavos
            .checked_add(centavos)
            .ok_or(ControlError::ArithmeticOverflow)?;
        self.top_up_receipts.insert(receipt.key());
        self.observed_top_ups_centavos = next;
        self.accounting_records.push(AccountingRecord::TopUp {
            centavos,
            receipt: receipt.clone(),
        });
        if self.halt.is_none()
            && (centavos > self.policy.top_up_centavos || next > self.policy.total_gas_centavos)
        {
            self.halt = Some(BudgetHalt::TopUpLimitBreached);
        }
        Ok(())
    }
    fn refresh_halt(&mut self) {
        if self.halt.is_some() {
            return;
        }
        self.halt = if self.gas_consumed_centavos >= self.policy.total_gas_centavos {
            Some(BudgetHalt::BudgetExhausted)
        } else if self.gas_consumed_centavos >= NO_CAPTURE_STOP_CENTAVOS
            && self.realized_capture_count == 0
        {
            Some(BudgetHalt::NoRealizedCapture)
        } else {
            None
        };
    }
}
