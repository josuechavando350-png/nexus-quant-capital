//! Fixed-size, by-value C ABI to unchanged R1 arithmetic. No unsafe Rust, heap,
//! I/O, shared mutable state, pointer dereferences, or process protocol.
#![deny(unsafe_op_in_unsafe_fn)]

use nqc_666_morpho_math::{math, uint::U256};

/// Six U256 arguments, each in four little-endian u64 limbs.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct Request {
    pub words: [u64; 24],
}

/// Status: 0 success, 1 input width, 17/18 unchanged arithmetic failure.
/// Failure responses are completely zero-initialized except for status.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Response {
    pub status: u64,
    pub debt: [u64; 4],
    pub capacity: [u64; 4],
    pub eligible: u64,
}

#[no_mangle]
pub extern "C" fn nqc666_abi_version() -> u64 {
    1
}

#[no_mangle]
pub extern "C" fn nqc666_health(request: Request) -> Response {
    let mut args = [U256::ZERO; 6];
    for (i, arg) in args.iter_mut().enumerate() {
        let j = i * 4;
        *arg = U256([
            request.words[j],
            request.words[j + 1],
            request.words[j + 2],
            request.words[j + 3],
        ]);
    }
    let (Some(assets), Some(total), Some(shares), Some(collateral), Some(lltv)) = (
        args[0].as_u128(),
        args[1].as_u128(),
        args[2].as_u128(),
        args[3].as_u128(),
        args[5].as_u128(),
    ) else {
        return Response {
            status: 1,
            ..Response::default()
        };
    };
    let input = math::HealthInput {
        total_borrow_assets: assets,
        total_borrow_shares: total,
        borrow_shares: shares,
        collateral,
        oracle_price: args[4],
        lltv,
    };
    match math::health::<true>(input) {
        Ok(h) => Response {
            status: 0,
            debt: h.debt.0,
            capacity: h.cap.0,
            eligible: u64::from(h.eligible),
        },
        Err(error) => Response {
            status: error as u64,
            ..Response::default()
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(values: [u128; 6]) -> Request {
        let mut r = Request::default();
        for (i, x) in values.into_iter().enumerate() {
            r.words[i * 4] = x as u64;
            r.words[i * 4 + 1] = (x >> 64) as u64;
        }
        r
    }
    #[test]
    fn fixed_abi_and_exact_boundary() {
        assert_eq!(core::mem::size_of::<Request>(), 192);
        assert_eq!(core::mem::size_of::<Response>(), 80);
        assert_eq!(nqc666_abi_version(), 1);
        let r = request([
            99,
            99_000_000,
            1_000_000,
            2,
            10u128.pow(36),
            10u128.pow(18) / 2,
        ]);
        let out = nqc666_health(r);
        assert_eq!(out.status, 0);
        assert_eq!(out.debt, [1, 0, 0, 0]);
        assert_eq!(out.capacity, [1, 0, 0, 0]);
        assert_eq!(out.eligible, 0);
        let mut changed = r;
        changed.words[8] += 1;
        assert_eq!(nqc666_health(changed).eligible, 1);
    }
    #[test]
    fn width_and_overflow_cannot_reuse_output() {
        let mut r = Request::default();
        r.words[2] = 1;
        assert_eq!(
            nqc666_health(r),
            Response {
                status: 1,
                ..Response::default()
            }
        );
        r = request([99, 99_000_000, 1, 2, 0, 10u128.pow(18) / 2]);
        r.words[16..20].fill(u64::MAX);
        assert_eq!(
            nqc666_health(r),
            Response {
                status: 17,
                ..Response::default()
            }
        );
    }
}
