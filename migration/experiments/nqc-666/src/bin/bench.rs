//! Linux x86_64 instrumentation ONLY. Unsafe is confined to clocks/cache intrinsics.
use nqc666::{
    engine::*,
    financial::{self},
    fixtures,
    prepared::Prepared,
    third_eye,
};
use std::{fs, hint::black_box, io::Write};
#[repr(C)]
struct Timespec {
    sec: i64,
    ns: i64,
}
unsafe extern "C" {
    fn clock_gettime(id: i32, p: *mut Timespec) -> i32;
}
fn tick() -> u64 {
    let mut t = Timespec { sec: 0, ns: 0 };
    assert_eq!(unsafe { clock_gettime(4, &mut t) }, 0);
    t.sec as u64 * 1_000_000_000 + t.ns as u64
}
#[cfg(target_arch = "x86_64")]
fn cycles() -> u64 {
    unsafe {
        std::arch::x86_64::_mm_lfence();
        let v = std::arch::x86_64::_rdtsc();
        std::arch::x86_64::_mm_lfence();
        v
    }
}
fn flush<T>(p: &T) {
    unsafe {
        let start = p as *const T as usize & !63;
        let end = p as *const T as usize + std::mem::size_of::<T>();
        for addr in (start..end).step_by(64) {
            std::arch::x86_64::_mm_clflush(addr as *const u8);
        }
        std::arch::x86_64::_mm_mfence();
    }
}
fn save(path: &str, v: &[u64]) {
    let mut f = fs::File::create(path).unwrap();
    for n in v {
        f.write_all(&n.to_le_bytes()).unwrap();
    }
}
// Explicit experiment knobs are kept outside the measured closure.
#[allow(clippy::too_many_arguments)]
fn run<T, R, F: FnMut(&T) -> R>(
    data: &[T],
    mut f: F,
    count: usize,
    seed: u64,
    out: &str,
    use_tsc: bool,
    batch: usize,
    cold: bool,
) where
    R: Consume,
{
    let mut rng = seed;
    let mut checksum = 0u64;
    let mut passes = 0u64;
    if batch > 1 {
        assert_eq!(data.len(), 256, "fixed 256-slot dependency chain");
    }
    for i in 0..10000 {
        checksum = checksum.wrapping_add(black_box(f(&data[i % data.len()])).consume());
    }
    let mut clock = Vec::with_capacity(10000);
    let mut samples = Vec::with_capacity(count);
    let mut ratios = Vec::new();
    for _ in 0..5 {
        let t = tick();
        let c = cycles();
        while tick() - t < 20_000_000 {
            std::hint::spin_loop();
        }
        ratios.push((cycles() - c) as f64 / (tick() - t) as f64);
    }
    let timer = if use_tsc { cycles } else { tick };
    for _ in 0..10000 {
        let a = timer();
        let b = timer();
        clock.push(b - a);
    }
    for _ in 0..count {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        let mut idx = rng as usize % 256;
        let input = black_box(&data[idx % data.len()]);
        if cold {
            flush(input);
        }
        // Dependency-chain batches are a separate metric: batch means, never call percentiles.
        let (elapsed, sum) = if batch == 1 {
            let start = timer();
            let r = black_box(f(input));
            let end = timer();
            (end - start, r.consume())
        } else {
            let start = timer();
            let mut sum = 0u64;
            for _ in 0..batch {
                let value = black_box(f(black_box(&data[idx]))).consume();
                sum = sum.wrapping_add(value);
                idx = (idx + 1 + (value as usize & 31)) & 255;
            }
            black_box(sum);
            (timer() - start, sum)
        };
        samples.push(elapsed);
        passes += u64::from(sum != 0);
        checksum = checksum.wrapping_add(sum);
    }
    save(&format!("{out}.bin"), &samples);
    save(&format!("{out}_clock.bin"), &clock);
    println!("{{\"samples\":{count},\"batch_size\":{batch},\"nonzero_samples\":{passes},\"checksum\":{checksum},\"tsc\":{use_tsc},\"tsc_ticks_per_ns\":{ratios:?},\"commercial_admission\":false}}");
}
trait Consume {
    fn consume(self) -> u64;
}
impl Consume for bool {
    fn consume(self) -> u64 {
        self as u64
    }
}
impl Consume for u64 {
    fn consume(self) -> u64 {
        self
    }
}
impl Consume for financial::Screen {
    fn consume(self) -> u64 {
        (self.total_funding as u64)
            ^ (self.total_operator_gas as u64)
            ^ (self.refunded as u64)
            ^ (self.residual as u64)
            ^ (self.sponsor_margin as u64)
            ^ self.reasons
    }
}
impl Consume for FinalCheck {
    fn consume(self) -> u64 {
        self.reasons ^ self.financial.consume()
    }
}
impl Consume for third_eye::Assessment {
    fn consume(self) -> u64 {
        self.observed as u64 ^ (self.prediction as u64) << 3
    }
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    assert_eq!(args.len(), 8, "bench CORPUS MODE COUNT SEED OUT TSC BATCH");
    let data: Vec<_> = fs::read_to_string(&args[1])
        .unwrap()
        .lines()
        .map(|s| financial::parse(s).unwrap())
        .collect();
    assert!(!data.is_empty());
    let mode = &args[2];
    let count = args[3].parse().unwrap();
    let seed = args[4].parse().unwrap();
    let out = &args[5];
    let tsc = args[6] == "1";
    let batch = args[7].parse().unwrap();
    assert!(batch == 1 || batch == 128);
    match mode.as_str() {
        "screen" | "flushed" => run(
            &data,
            financial::screen,
            count,
            seed,
            out,
            tsc,
            batch,
            mode == "flushed",
        ),
        "prepare" => run(
            &data,
            |c| black_box(Prepared::new(c)).is_some(),
            count,
            seed,
            out,
            tsc,
            batch,
            false,
        ),
        "branchy" | "packed" => {
            let probes: Vec<_> = data
                .iter()
                .enumerate()
                .map(|(k, c)| {
                    let time = match k % 4 {
                        0 => c.received_ns - 1,
                        1 => c.now_ns,
                        2 => c.quote_expiry_ns,
                        _ => c.now_ns,
                    };
                    (
                        Prepared::new(c).unwrap(),
                        c.epoch + u64::from(k % 11 == 0),
                        time,
                    )
                })
                .collect();
            if mode == "packed" {
                run(
                    &probes,
                    |p| p.0.packed(p.1, p.2),
                    count,
                    seed,
                    out,
                    tsc,
                    batch,
                    false,
                )
            } else {
                run(
                    &probes,
                    |p| p.0.branchy(p.1, p.2),
                    count,
                    seed,
                    out,
                    tsc,
                    batch,
                    false,
                )
            }
        }
        "compact" | "compact_inline" | "chain_control" => {
            let probes: Vec<_> = data
                .iter()
                .enumerate()
                .map(|(k, c)| {
                    let time = match k % 4 {
                        0 => c.received_ns - 1,
                        1 => c.now_ns,
                        2 => c.quote_expiry_ns,
                        _ => c.now_ns,
                    };
                    (
                        Prepared::new(c).unwrap().compact(),
                        c.epoch + u64::from(k % 11 == 0),
                        time,
                    )
                })
                .collect();
            if mode == "compact_inline" {
                run(
                    &probes,
                    |p| p.0.ready_inline(p.1, p.2),
                    count,
                    seed,
                    out,
                    tsc,
                    batch,
                    false,
                )
            } else if mode == "compact" {
                run(
                    &probes,
                    |p| p.0.ready(p.1, p.2),
                    count,
                    seed,
                    out,
                    tsc,
                    batch,
                    false,
                )
            } else {
                run(
                    &probes,
                    |p| (p.1 & 1) != 0,
                    count,
                    seed,
                    out,
                    tsc,
                    batch,
                    false,
                )
            }
        }
        "guard" | "guard_copy" => {
            let u: Vec<_> = data
                .iter()
                .enumerate()
                .map(|(k, c)| fixtures::update(c.clone(), k))
                .collect();
            if mode == "guard" {
                run(
                    &u,
                    |x| guard(x, x.integrity.anchor, x.financial.now_ns),
                    count,
                    seed,
                    out,
                    tsc,
                    batch,
                    false,
                )
            } else {
                run(
                    &u,
                    |x| guard_copy(x, x.integrity.anchor, x.financial.now_ns),
                    count,
                    seed,
                    out,
                    tsc,
                    batch,
                    false,
                )
            };
        }
        "eye" => {
            let u: Vec<_> = data
                .iter()
                .enumerate()
                .map(|(k, c)| fixtures::update(c.clone(), k))
                .collect();
            run(
                &u,
                |x| third_eye::assess(x.position, x.scenario, x.financial.now_ns),
                count,
                seed,
                out,
                tsc,
                batch,
                false,
            );
        }
        "event" | "event_reference" | "event_final" | "event_reference_final" => {
            let u: Vec<_> = (0..256)
                .map(|k| fixtures::update(data[k % data.len()].clone(), k))
                .collect();
            let mut engine = Engine::new(
                u[0].integrity.anchor,
                u.iter().map(|x| x.integrity.key).collect(),
            )
            .unwrap();
            let events: Vec<_> = u.into_iter().enumerate().collect();
            run(
                &events,
                |(k, input)| {
                    let x = black_box(input.clone());
                    let now = x.financial.now_ns;
                    let r = if mode.contains("reference") {
                        engine.on_event_reference(*k, x, now)
                    } else {
                        engine.on_event(*k, x, now)
                    };
                    let a = black_box(r).unwrap();
                    let ticket = black_box(engine.candidate(now));
                    let final_reason = if mode.ends_with("final") {
                        ticket
                            .map(|t| {
                                let check = if mode.contains("reference") {
                                    engine.finalize_reference(t, now)
                                } else {
                                    engine.finalize(t, now)
                                };
                                black_box(check).reasons
                            })
                            .unwrap_or(u64::MAX)
                    } else {
                        0
                    };
                    (a.observed as u64)
                        ^ (ticket.map(|t| t.slot() as u64 + 1).unwrap_or(0))
                        ^ final_reason
                },
                count,
                seed,
                out,
                tsc,
                batch,
                false,
            );
        }
        _ => panic!("unknown mode"),
    }
}
