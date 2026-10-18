use crate::{
    financial::{self, Candidate, Screen},
    prepared::{Compact, Prepared},
    third_eye::{self, Assessment, Observed, Position, Scenario},
};
pub const CAPACITY: usize = 256;
pub const GUARD_IDENTITY: u64 = 1 << 32;
pub const GUARD_ORACLE: u64 = 1 << 33;
pub const GUARD_EXECUTION: u64 = 1 << 34;
pub const GUARD_EXTERNAL: u64 = 1 << 35;
pub const GUARD_PRICE: u64 = 1 << 36;
pub const GUARD_ELIGIBILITY: u64 = 1 << 37;
pub const GUARD_STALE: u64 = 1 << 38;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Key {
    pub market: [u8; 32],
    pub borrower: [u8; 20],
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Anchor {
    pub chain: u64,
    pub block: u64,
    pub hash: [u8; 32],
}
#[derive(Clone, Debug)]
pub struct Integrity {
    pub key: Key,
    pub anchor: Anchor,
    pub plan_hash: [u8; 32],
    pub code_hash: [u8; 32],
    pub required_code_hash: [u8; 32],
    pub oracle_at: u64,
    pub oracle_max_age: u64,
    pub route_through: u64,
    pub nonce_start: u64,
    pub nonces: [u64; 16],
    pub dependencies: [u16; 16],
    pub success_mask: u16,
    pub required_builder_payment: u128,
    pub builder_paid: u128,
    pub slippage_bps: u16,
    pub max_slippage_bps: u16,
    pub quoted_net_lower: Option<u128>,
    pub financing_confirmed: Option<bool>,
    pub non_recourse: Option<bool>,
}
#[derive(Clone, Debug)]
pub struct Update {
    pub financial: Candidate,
    pub integrity: Integrity,
    pub position: Position,
    pub scenario: Option<Scenario>,
    pub inclusion_ppm: Option<u32>,
    pub failure_loss: Option<u128>,
}
#[derive(Clone, Debug)]
struct Entry {
    update: Update,
    prepared: Option<Compact>,
    assessment: Assessment,
    generation: u64,
}
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Rank {
    score: u128,
    slot: usize,
}
fn better(a: Rank, b: Rank) -> Rank {
    if a.score > b.score || (a.score == b.score && a.slot < b.slot) {
        a
    } else {
        b
    }
}
#[derive(Clone, Copy, Debug)]
pub struct Ticket {
    slot: usize,
    generation: u64,
    anchor: Anchor,
}
impl Ticket {
    pub fn slot(self) -> usize {
        self.slot
    }
}
#[derive(Clone, Copy, Debug)]
pub struct FinalCheck {
    pub reasons: u64,
    pub financial: Screen,
    pub commercial_admission: bool,
}
fn oracle_window(i: &Integrity, now: u64, budget: u64) -> bool {
    let Some(end) = now.checked_add(budget) else {
        return false;
    };
    i.oracle_at > 0
        && i.oracle_max_age > 0
        && budget > 0
        && now >= i.oracle_at
        && end - i.oracle_at <= i.oracle_max_age
        && end < i.route_through
}

/// Single owner, bounded slots, binary tournament tree: exactly 8 ancestor updates.
/// Setup allocations only; no network, locks, threads, queues or unsafe code.
pub struct Engine {
    anchor: Anchor,
    keys: Vec<Key>,
    entries: Vec<Option<Entry>>,
    generations: [u64; CAPACITY],
    tree: [Rank; CAPACITY * 2],
}
impl Engine {
    pub fn new(anchor: Anchor, keys: Vec<Key>) -> Result<Self, &'static str> {
        if keys.len() > CAPACITY || anchor.chain != 1 || anchor.block == 0 || anchor.hash == [0; 32]
        {
            return Err("invalid registry/anchor");
        }
        for (i, k) in keys.iter().enumerate() {
            if k.market == [0; 32] || k.borrower == [0; 20] || keys[..i].contains(k) {
                return Err("invalid key");
            }
        }
        let entries = vec![None; keys.len()];
        Ok(Self {
            anchor,
            keys,
            entries,
            generations: [0; CAPACITY],
            tree: [Rank::default(); CAPACITY * 2],
        })
    }
    fn rank(&mut self, slot: usize, score: u128) {
        let mut i = CAPACITY + slot;
        self.tree[i] = Rank { score, slot };
        while i > 1 {
            i /= 2;
            self.tree[i] = better(self.tree[i * 2], self.tree[i * 2 + 1]);
        }
    }
    /// Any block change or reorg invalidates ALL prepared entries. No generation reuse.
    pub fn reset_anchor(&mut self, anchor: Anchor) -> Result<(), &'static str> {
        if anchor.chain != 1 || anchor.block == 0 || anchor.hash == [0; 32] {
            return Err("invalid anchor");
        }
        self.anchor = anchor;
        self.entries.fill(None);
        self.tree.fill(Rank::default());
        Ok(())
    }
    /// A complete decoded update must include every field changed by the event.
    /// Invalid updates invalidate the old entry BEFORE returning an error.
    pub fn on_event(
        &mut self,
        slot: usize,
        u: Update,
        now: u64,
    ) -> Result<Assessment, &'static str> {
        self.apply(slot, u, now, false)
    }
    /// Equivalent reference path, retaining the redundant financial pre-screen.
    pub fn on_event_reference(
        &mut self,
        slot: usize,
        u: Update,
        now: u64,
    ) -> Result<Assessment, &'static str> {
        self.apply(slot, u, now, true)
    }
    fn apply(
        &mut self,
        slot: usize,
        mut u: Update,
        now: u64,
        redundant: bool,
    ) -> Result<Assessment, &'static str> {
        if slot >= self.keys.len() {
            return Err("unknown slot");
        }
        self.entries[slot] = None;
        self.rank(slot, 0);
        let Some(g) = self.generations[slot].checked_add(1) else {
            return Err("generation exhausted");
        };
        self.generations[slot] = g;
        if u.integrity.key != self.keys[slot] || u.integrity.anchor != self.anchor {
            return Err("identity mismatch");
        }
        u.financial.epoch = g;
        u.financial.current_epoch = g;
        u.financial.now_ns = now;
        let assessment = third_eye::assess(u.position, u.scenario, now);
        let check = if redundant {
            guard_copy(&u, self.anchor, now)
        } else {
            guard(&u, self.anchor, now)
        };
        let prepared = if redundant {
            Prepared::new(&u.financial)
        } else {
            Prepared::from_screen(&u.financial, check.financial)
        };
        let prepared = prepared.map(Prepared::compact);
        let score = if assessment.observed == Observed::Eligible && check.reasons == 0 {
            third_eye::expected_net(
                u.integrity.quoted_net_lower.unwrap_or(0),
                u.inclusion_ppm,
                u.failure_loss,
            )
            .unwrap_or(0)
        } else {
            0
        };
        self.entries[slot] = Some(Entry {
            update: u,
            prepared,
            assessment,
            generation: g,
        });
        self.rank(slot, score);
        Ok(assessment)
    }
    /// Expires stale leaders lazily; worst-case O(CAPACITY log CAPACITY), bounded.
    pub fn candidate(&mut self, now: u64) -> Option<Ticket> {
        for _ in 0..self.keys.len() {
            let r = self.tree[1];
            if r.score == 0 {
                return None;
            }
            let e = self.entries[r.slot].as_ref()?;
            let i = &e.update.integrity;
            let oracle_valid = oracle_window(i, now, e.update.financial.send_budget_ns);
            if e.prepared
                .as_ref()
                .is_some_and(|p| p.ready_inline(e.generation, now))
                && oracle_valid
                && now <= i.route_through
            {
                return Some(Ticket {
                    slot: r.slot,
                    generation: e.generation,
                    anchor: self.anchor,
                });
            }
            self.rank(r.slot, 0);
        }
        None
    }
    pub fn finalize(&self, t: Ticket, now: u64) -> FinalCheck {
        self.finalize_impl(t, now, false)
    }
    pub fn finalize_reference(&self, t: Ticket, now: u64) -> FinalCheck {
        self.finalize_impl(t, now, true)
    }
    fn finalize_impl(&self, t: Ticket, now: u64, copy: bool) -> FinalCheck {
        let stale = FinalCheck {
            reasons: GUARD_STALE,
            financial: Screen::default(),
            commercial_admission: false,
        };
        if t.anchor != self.anchor {
            return stale;
        }
        let Some(e) = self.entries.get(t.slot).and_then(Option::as_ref) else {
            return stale;
        };
        if e.generation != t.generation || e.assessment.observed != Observed::Eligible {
            return stale;
        }
        if copy {
            guard_copy(&e.update, self.anchor, now)
        } else {
            guard(&e.update, self.anchor, now)
        }
    }
}

/// Recomputes the entire financial screen on an immutable copy, then all supplemental
/// local guards. Supplied hashes/terms are NOT authenticated here. Always research-only.
#[inline(never)]
pub fn guard(u: &Update, anchor: Anchor, now: u64) -> FinalCheck {
    finish_guard(u, anchor, now, financial::screen_at(&u.financial, now))
}
#[inline(never)]
pub fn guard_copy(u: &Update, anchor: Anchor, now: u64) -> FinalCheck {
    let mut copied = u.financial.clone();
    copied.now_ns = now;
    finish_guard(u, anchor, now, financial::screen(&copied))
}
#[inline(always)]
fn finish_guard(u: &Update, anchor: Anchor, now: u64, financial: Screen) -> FinalCheck {
    let c = &u.financial;
    let mut reasons = financial.reasons;
    let i = &u.integrity;
    if i.anchor != anchor
        || c.chain_id != anchor.chain
        || c.block_number != anchor.block
        || c.state_hashes[0] != anchor.hash
        || i.key.market == [0; 32]
        || i.key.borrower == [0; 20]
        || i.plan_hash == [0; 32]
        || i.code_hash == [0; 32]
        || i.code_hash != i.required_code_hash
    {
        reasons |= GUARD_IDENTITY;
    }
    if !oracle_window(i, now, c.send_budget_ns) {
        reasons |= GUARD_ORACLE;
    }
    if c.n == 0 || c.n > 16 {
        reasons |= GUARD_EXECUTION;
    } else {
        let mask = ((1u32 << c.n) - 1) as u16;
        if i.success_mask != mask || i.nonce_start.checked_add(c.n).is_none() {
            reasons |= GUARD_EXECUTION;
        }
        for k in 0..c.n as usize {
            let previous = ((1u32 << k) - 1) as u16;
            if i.nonce_start.checked_add(k as u64) != Some(i.nonces[k])
                || i.dependencies[k] & !previous != 0
            {
                reasons |= GUARD_EXECUTION;
            }
        }
    }
    if i.builder_paid < i.required_builder_payment || i.builder_paid > c.other_costs {
        reasons |= GUARD_EXECUTION;
    }
    if i.non_recourse != Some(true) || i.financing_confirmed != Some(true) {
        reasons |= GUARD_EXTERNAL;
    }
    if i.max_slippage_bps > 10000
        || i.slippage_bps > i.max_slippage_bps
        || i.quoted_net_lower
            .is_none_or(|v| v == 0 || v < c.min_operator_weth || v > c.operator_weth_new)
    {
        reasons |= GUARD_PRICE;
    }
    if third_eye::assess(u.position, None, now).observed != Observed::Eligible {
        reasons |= GUARD_ELIGIBILITY;
    }
    FinalCheck {
        reasons,
        financial,
        commercial_admission: false,
    }
}
