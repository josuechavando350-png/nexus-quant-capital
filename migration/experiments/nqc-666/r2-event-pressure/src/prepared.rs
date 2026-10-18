use crate::financial::{screen, Candidate, Screen};

/// Immutable 32-byte temporal prefilter. Constructible only by a successful full screen.
/// Epoch must identify a complete immutable snapshot, including policy and financing inputs.
/// It is NOT a financial or commercial authorization. A final full screen is mandatory.
#[derive(Clone, Copy, Debug)]
#[repr(C)]
pub struct Prepared {
    epoch: u64,
    not_before: u64,
    through: u64,
    ready: u64,
}
/// 24-byte form: successful construction makes the old `ready == 1` field redundant.
/// No check is dropped: the construction invariant replaces the repeated constant test.
#[derive(Clone, Copy, Debug)]
#[repr(C)]
pub struct Compact {
    epoch: u64,
    not_before: u64,
    through: u64,
}
impl Compact {
    #[inline(never)]
    pub fn ready(&self, epoch: u64, now: u64) -> bool {
        self.ready_inline(epoch, now)
    }
    /// Same checks; intended for the hot caller. Benchmark inputs/outputs remain opaque.
    #[inline(always)]
    pub fn ready_inline(&self, epoch: u64, now: u64) -> bool {
        self.epoch == epoch && now >= self.not_before && now <= self.through
    }
}
impl Prepared {
    pub fn compact(self) -> Compact {
        Compact {
            epoch: self.epoch,
            not_before: self.not_before,
            through: self.through,
        }
    }
    pub fn new(c: &Candidate) -> Option<Self> {
        Self::from_screen(c, screen(c))
    }
    /// Caller inside this crate must have just screened this exact immutable candidate.
    pub(crate) fn from_screen(c: &Candidate, checked: Screen) -> Option<Self> {
        if checked.reasons != 0 {
            return None;
        }
        Some(Self {
            epoch: c.epoch,
            not_before: c.received_ns,
            through: c
                .received_ns
                .saturating_add(c.max_age_ns)
                .min(c.cutoff_ns.checked_sub(c.send_budget_ns)?.checked_sub(1)?)
                .min(
                    c.quote_expiry_ns
                        .checked_sub(c.send_budget_ns)?
                        .checked_sub(1)?,
                ),
            ready: 1,
        })
    }
    #[inline(never)]
    pub fn branchy(&self, epoch: u64, now: u64) -> bool {
        self.ready == 1 && self.epoch == epoch && now >= self.not_before && now <= self.through
    }
    #[inline(never)]
    pub fn packed(&self, epoch: u64, now: u64) -> bool {
        (self.ready == 1) & (self.epoch == epoch) & (now >= self.not_before) & (now <= self.through)
    }
}
