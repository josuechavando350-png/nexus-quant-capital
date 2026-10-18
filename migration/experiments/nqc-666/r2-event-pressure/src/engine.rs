use crate::{
    financial::Screen,
    prepared::{Compact, Prepared},
    third_eye::{self, Assessment, Observed},
};
pub const CAPACITY: usize = 256;
pub const GUARD_IDENTITY: u64 = 1 << 32;
pub const GUARD_ORACLE: u64 = 1 << 33;
pub const GUARD_EXECUTION: u64 = 1 << 34;
pub const GUARD_EXTERNAL: u64 = 1 << 35;
pub const GUARD_PRICE: u64 = 1 << 36;
pub const GUARD_ELIGIBILITY: u64 = 1 << 37;
pub const GUARD_STALE: u64 = 1 << 38;

pub use nqc666::engine::{guard, guard_copy, Anchor, FinalCheck, Integrity, Key, Update};

#[derive(Clone, Debug)]
struct Entry {
    update: Update,
    prepared: Option<Compact>,
    assessment: Assessment,
    generation: u64,
}

#[cfg(test)]
mod tests {
    use super::*;
    fn exhausted<const B: bool, const S: bool>() {
        let u = nqc666::fixtures::update(nqc666::fixtures::financial(4, 666), 0);
        let mut e = Engine::<B, S>::new(u.integrity.anchor, vec![u.integrity.key]).unwrap();
        e.on_event(0, u.clone(), 200_000).unwrap();
        let t = e.candidate(200_000).unwrap();
        e.generations[0] = u64::MAX;
        assert_eq!(e.on_event(0, u, 200_000), Err("generation exhausted"));
        assert!(e.candidate(200_000).is_none());
        assert_eq!(e.finalize(t, 200_000).reasons, GUARD_STALE);
        assert_eq!(e.tree[1].score, 0);
    }
    #[test]
    fn all_variants_fail_closed_on_exhausted_generation() {
        exhausted::<false, false>();
        exhausted::<false, true>();
        exhausted::<true, false>();
        exhausted::<true, true>();
    }
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
pub struct Engine<const BULK: bool = true, const SINGLE_WRITE: bool = true> {
    anchor: Anchor,
    keys: Vec<Key>,
    entries: Vec<Option<Entry>>,
    generations: [u64; CAPACITY],
    tree: [Rank; CAPACITY * 2],
}
impl<const BULK: bool, const SINGLE_WRITE: bool> Engine<BULK, SINGLE_WRITE> {
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
        if !SINGLE_WRITE {
            self.rank(slot, 0);
        }
        let Some(g) = self.generations[slot].checked_add(1) else {
            if SINGLE_WRITE {
                self.rank(slot, 0);
            }
            return Err("generation exhausted");
        };
        self.generations[slot] = g;
        if u.integrity.key != self.keys[slot] || u.integrity.anchor != self.anchor {
            if SINGLE_WRITE {
                self.rank(slot, 0);
            }
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
    fn current(&self, r: Rank, now: u64) -> bool {
        let Some(e) = self.entries[r.slot].as_ref() else {
            return false;
        };
        let i = &e.update.integrity;
        e.prepared
            .as_ref()
            .is_some_and(|p| p.ready_inline(e.generation, now))
            && oracle_window(i, now, e.update.financial.send_budget_ns)
            && now <= i.route_through
    }
    fn ticket(&self, r: Rank) -> Ticket {
        Ticket {
            slot: r.slot,
            generation: self.entries[r.slot].as_ref().unwrap().generation,
            anchor: self.anchor,
        }
    }
    /// Ordinary lazy selection, with optional linear recovery after 64 expired leaders.
    /// Inspect the next leader before recovering, so exactly 64 expirations stay cheap.
    pub fn candidate(&mut self, now: u64) -> Option<Ticket> {
        for removed in 0..=self.keys.len() {
            let r = self.tree[1];
            if r.score == 0 {
                return None;
            }
            if self.current(r, now) {
                return Some(self.ticket(r));
            }
            if BULK && removed == 64 {
                return self.recover(now);
            }
            self.rank(r.slot, 0);
        }
        None
    }
    #[inline(never)]
    fn recover(&mut self, now: u64) -> Option<Ticket> {
        let mut winner = Rank::default();
        for slot in 0..self.keys.len() {
            let r = self.tree[CAPACITY + slot];
            if r.score > 0 && better(r, winner) == r && self.current(r, now) {
                winner = r;
            }
        }
        for r in &mut self.tree[CAPACITY..CAPACITY + self.keys.len()] {
            if r.score > 0 && (winner.score == 0 || (*r != winner && better(*r, winner) == *r)) {
                r.score = 0;
            }
        }
        for node in (1..CAPACITY).rev() {
            self.tree[node] = better(self.tree[node * 2], self.tree[node * 2 + 1]);
        }
        (winner.score > 0).then(|| self.ticket(winner))
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
