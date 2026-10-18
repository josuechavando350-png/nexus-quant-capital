//! Individual clock windows; whole result and mutated engine escape before stop.
use nqc666::{
    engine::{Anchor, FinalCheck, Key, Update},
    third_eye::Assessment,
};
use nqc_666_event_pressure::{engine as new, fixtures};
use nqc_666_morpho_math::adapter::Snapshot;
use std::{fs, hint::black_box, io::Write};
#[repr(C)]
struct Timespec {
    sec: i64,
    ns: i64,
}
unsafe extern "C" {
    fn clock_gettime(clock: i32, p: *mut Timespec) -> i32;
}
fn tick() -> u64 {
    let mut t = Timespec { sec: 0, ns: 0 };
    assert_eq!(unsafe { clock_gettime(4, &mut t) }, 0);
    t.sec as u64 * 1_000_000_000 + t.ns as u64
}
fn write(path: &str, data: &[u64]) {
    let mut f = fs::File::create(path).unwrap();
    for v in data {
        f.write_all(&v.to_le_bytes()).unwrap();
    }
}
trait LocalEngine {
    fn new(anchor: Anchor, keys: Vec<Key>) -> Self;
    fn event(&mut self, slot: usize, u: Update, now: u64) -> Assessment;
    fn snapshot(&mut self, slot: usize, s: Snapshot, u: Update, now: u64) -> Assessment;
    fn finish(&mut self, now: u64) -> Option<(usize, FinalCheck)>;
}
impl LocalEngine for nqc666::engine::Engine {
    fn new(a: Anchor, keys: Vec<Key>) -> Self {
        Self::new(a, keys).unwrap()
    }
    fn event(&mut self, slot: usize, u: Update, now: u64) -> Assessment {
        self.on_event(slot, u, now).unwrap()
    }
    fn snapshot(&mut self, slot: usize, s: Snapshot, u: Update, now: u64) -> Assessment {
        nqc_666_morpho_math::adapter::on_snapshot::<true>(self, slot, s, u, now).unwrap()
    }
    fn finish(&mut self, now: u64) -> Option<(usize, FinalCheck)> {
        self.candidate(now)
            .map(|t| (t.slot(), self.finalize(t, now)))
    }
}
impl<const B: bool, const S: bool> LocalEngine for new::Engine<B, S> {
    fn new(a: Anchor, keys: Vec<Key>) -> Self {
        Self::new(a, keys).unwrap()
    }
    fn event(&mut self, slot: usize, u: Update, now: u64) -> Assessment {
        self.on_event(slot, u, now).unwrap()
    }
    fn snapshot(&mut self, slot: usize, s: Snapshot, u: Update, now: u64) -> Assessment {
        nqc_666_event_pressure::adapter::on_snapshot::<true, B, S>(self, slot, s, u, now).unwrap()
    }
    fn finish(&mut self, now: u64) -> Option<(usize, FinalCheck)> {
        self.candidate(now)
            .map(|t| (t.slot(), self.finalize(t, now)))
    }
}
struct Output {
    event: Option<(usize, Assessment)>,
    final_result: Option<(usize, FinalCheck)>,
}
fn mix(a: u64, b: u64) -> u64 {
    a.rotate_left(7) ^ b
}
fn amount(a: u64, v: u128) -> u64 {
    mix(mix(a, v as u64), (v >> 64) as u64)
}
impl Output {
    fn consume(self) -> u64 {
        let mut v = 0;
        if let Some((slot, a)) = self.event {
            v = mix(
                mix(mix(slot as u64, a.basis as u64), a.observed as u64),
                a.prediction as u64,
            );
        }
        if let Some((slot, f)) = self.final_result {
            v = mix(
                mix(mix(v, slot as u64), f.reasons),
                u64::from(f.commercial_admission),
            );
            v = mix(v, f.financial.reasons);
            for x in [
                f.financial.total_funding,
                f.financial.total_operator_gas,
                f.financial.refunded,
                f.financial.residual,
                f.financial.sponsor_margin,
            ] {
                v = amount(v, x);
            }
        }
        v
    }
}
fn fill<E: LocalEngine>(e: &mut E, rows: &[Update]) {
    for (slot, u) in rows.iter().enumerate() {
        black_box(e.event(slot, u.clone(), fixtures::INSERT_AT));
    }
}
fn run<E: LocalEngine>(mode: &str, expired: usize, count: usize, seed: u64, out: &str) {
    assert!(
        expired < 256,
        "varying survivor required; complete expiry tested separately"
    );
    let sets: Vec<_> = (0..32)
        .map(|n| fixtures::burst(expired, seed + 7919 * n))
        .collect();
    let morpho: Vec<_> = (0..256).map(nqc_666_morpho_math::fixtures::row).collect();
    let mut engine = E::new(
        sets[0].0[0].integrity.anchor,
        sets[0].0.iter().map(|u| u.integrity.key).collect(),
    );
    let mut samples = Vec::with_capacity(count);
    let mut controls = Vec::with_capacity(10_000);
    for _ in 0..10_000 {
        let a = tick();
        let b = tick();
        controls.push(b - a);
    }
    let mut rng = seed;
    let mut sum = 0u64;
    let mut distinct = std::collections::BTreeSet::new();
    let mut valid = 0usize;
    for k in 0..count + 1024 {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        let index = black_box(rng as usize);
        let (rows, now) = black_box(&sets[index % sets.len()]);
        if mode == "select" {
            fill(&mut engine, rows);
        }
        let a = tick();
        let event = match mode {
            "select" => None,
            "cycle" => {
                fill(&mut engine, rows);
                None
            }
            "pipeline" => {
                let slot = index % 256;
                let (s, u) = black_box(&morpho[slot]);
                Some((
                    slot,
                    engine.snapshot(slot, *s, u.clone(), u.financial.now_ns),
                ))
            }
            _ => panic!("unknown mode"),
        };
        let time = if mode == "pipeline" { 200_000 } else { *now };
        let output = black_box(Output {
            event,
            final_result: engine.finish(time),
        });
        // Mutable reference makes ALL state writes observable, including pruned ranks.
        black_box(&mut engine);
        let b = tick();
        if let Some((_, f)) = &output.final_result {
            assert_eq!(f.reasons, 0);
            assert!(!f.commercial_admission);
            valid += 1;
        }
        let value = output.consume();
        sum = sum.wrapping_add(value);
        if k < 1024 {
            distinct.insert(value);
        } else {
            samples.push(b - a);
        }
    }
    assert!(distinct.len() > 1, "constant observed outputs");
    write(&format!("{out}.bin"), &samples);
    write(&format!("{out}_clock.bin"), &controls);
    println!("{{\"samples\":{count},\"checksum\":{sum},\"distinct_warm_outputs\":{},\"valid_including_warm\":{valid},\"commercial_admission\":false,\"batch_size\":1}}",distinct.len());
}
fn main() {
    let a: Vec<_> = std::env::args().collect();
    assert_eq!(a.len(), 7, "bench MODE VARIANT EXPIRED COUNT SEED OUT");
    let expired = a[3].parse().unwrap();
    let count = a[4].parse().unwrap();
    let seed = a[5].parse().unwrap();
    match a[2].as_str() {
        "original" => run::<nqc666::engine::Engine>(&a[1], expired, count, seed, &a[6]),
        "combined" => run::<new::Engine<true, true>>(&a[1], expired, count, seed, &a[6]),
        "batch" => run::<new::Engine<true, false>>(&a[1], expired, count, seed, &a[6]),
        "single" => run::<new::Engine<false, true>>(&a[1], expired, count, seed, &a[6]),
        _ => panic!("unknown variant"),
    }
}
