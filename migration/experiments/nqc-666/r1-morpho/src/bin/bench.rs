//! CLOCK_MONOTONIC_RAW, one observable result per measured call, no subtraction/filtering.
use nqc666::{
    engine::{Engine, FinalCheck},
    third_eye::{Assessment, Position},
};
use nqc_666_morpho_math::{adapter, fixtures, math};
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
trait Consume {
    fn consume(self) -> u64;
}
fn mix(a: u64, b: u64) -> u64 {
    a.rotate_left(7) ^ b
}
fn amount(a: u64, v: u128) -> u64 {
    mix(mix(a, v as u64), (v >> 64) as u64)
}
impl Consume for math::Health {
    fn consume(self) -> u64 {
        self.debt
            .0
            .iter()
            .chain(self.cap.0.iter())
            .fold(u64::from(self.eligible), |a, b| mix(a, *b))
    }
}
impl Consume for Position {
    fn consume(self) -> u64 {
        amount(
            amount(self.basis as u64 ^ self.near_bps as u64, self.debt.unwrap()),
            self.max_borrow.unwrap(),
        )
    }
}
struct PipelineOutput {
    updated_slot: usize,
    assessment: Assessment,
    final_result: Option<(usize, FinalCheck)>,
}
impl Consume for PipelineOutput {
    fn consume(self) -> u64 {
        let mut v = mix(self.updated_slot as u64, self.assessment.observed as u64);
        v = mix(
            mix(v, self.assessment.basis as u64),
            self.assessment.prediction as u64,
        );
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
fn measure<R: Consume, F: FnMut(usize) -> R>(mut f: F, count: usize, seed: u64, out: &str) {
    let mut sum = 0u64;
    let mut rng = seed;
    let mut distinct = std::collections::BTreeSet::new();
    for k in 0..10000 {
        let value = black_box(f(k % 256)).consume();
        sum = sum.wrapping_add(value);
        distinct.insert(value);
    }
    let mut clock = Vec::with_capacity(10000);
    for _ in 0..10000 {
        let a = tick();
        let b = tick();
        clock.push(b - a);
    }
    let mut times = Vec::with_capacity(count);
    let mut nonzero = 0u64;
    for _ in 0..count {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        let k = black_box(rng as usize % 256);
        let a = tick();
        let result = black_box(f(k));
        let b = tick();
        let result = result.consume();
        times.push(b - a);
        sum = sum.wrapping_add(result);
        nonzero += u64::from(result != 0);
    }
    let distinct = distinct.len();
    assert!(distinct > 1, "constant-output benchmark rejected");
    write(&format!("{out}.bin"), &times);
    write(&format!("{out}_clock.bin"), &clock);
    println!("{{\"distinct_warm_outputs\":{distinct},\"checksum\":{sum},\"nonzero\":{nonzero},\"samples\":{count},\"batch_size\":1,\"commercial_admission\":false}}");
}
fn run<const FAST: bool>(mode: &str, count: usize, seed: u64, out: &str) {
    let rows: Vec<_> = (0..256).map(fixtures::row).collect();
    match mode {
        "math" => measure(
            |k| {
                let s = black_box(&rows[k].0);
                math::health::<FAST>(s.math).unwrap()
            },
            count,
            seed,
            out,
        ),
        "adapter" => measure(
            |k| {
                let s = black_box(&rows[k].0);
                adapter::position::<FAST>(*s, s.key, s.anchor, 100).unwrap()
            },
            count,
            seed,
            out,
        ),
        "pipeline" => {
            let mut engine =
                Engine::new(rows[0].0.anchor, rows.iter().map(|r| r.0.key).collect()).unwrap();
            measure(
                |k| {
                    let (s, u) = black_box(&rows[k]);
                    let now = u.financial.now_ns;
                    let assessment =
                        adapter::on_snapshot::<FAST>(&mut engine, k, *s, u.clone(), now).unwrap();
                    let final_result = engine
                        .candidate(now)
                        .map(|t| (t.slot(), engine.finalize(t, now)));
                    PipelineOutput {
                        updated_slot: k,
                        assessment,
                        final_result,
                    }
                },
                count,
                seed,
                out,
            );
        }
        _ => panic!("unknown mode"),
    }
}
fn main() {
    let a: Vec<_> = std::env::args().collect();
    assert_eq!(a.len(), 6, "bench MODE FAST COUNT SEED OUT");
    let count = a[3].parse().unwrap();
    let seed = a[4].parse().unwrap();
    match a[2].as_str() {
        "1" => run::<true>(&a[1], count, seed, &a[5]),
        "0" => run::<false>(&a[1], count, seed, &a[5]),
        _ => panic!("FAST must be 0/1"),
    }
}
