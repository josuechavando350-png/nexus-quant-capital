use nqc_666_morpho_math::{
    math::{self, HealthInput, Market, Rate},
    uint::U256,
};
use std::io::{self, BufRead};
fn eval<const FAST: bool>(line: &str) -> Option<String> {
    let mut it = line.split_whitespace();
    let op = it.next()?;
    let a: Vec<_> = it.map(U256::from_hex).collect::<Option<_>>()?;
    let result = match (op, a.as_slice()) {
        ("D", [x, y, d, up]) if *up <= 1u128.into() => {
            math::mul_div::<FAST>(*x, *y, *d, *up != U256::ZERO).map(|v| vec![v])
        }
        ("A", [s, assets, total, up]) if *up <= 1u128.into() => {
            math::to_assets::<FAST>(*s, *assets, *total, *up != U256::ZERO).map(|v| vec![v])
        }
        ("T", [r, t]) => math::taylor::<FAST>(*r, *t).map(|v| vec![v]),
        ("H", [assets, total, shares, collateral, price, lltv]) => {
            math::health::<FAST>(HealthInput {
                total_borrow_assets: assets.as_u128()?,
                total_borrow_shares: total.as_u128()?,
                borrow_shares: shares.as_u128()?,
                collateral: collateral.as_u128()?,
                oracle_price: *price,
                lltv: lltv.as_u128()?,
            })
            .map(|h| vec![h.debt, h.cap, U256::from(u128::from(h.eligible))])
        }
        ("P", [sa, ss, ba, bs, last, fee, now, kind, rate]) => {
            let m = Market {
                supply_assets: sa.as_u128()?,
                supply_shares: ss.as_u128()?,
                borrow_assets: ba.as_u128()?,
                borrow_shares: bs.as_u128()?,
                last_update_s: last.as_u128()?.try_into().ok()?,
                fee: fee.as_u128()?,
            };
            let rate = match kind.as_u128()? {
                0 => Rate::Unknown,
                1 => Rate::ZeroIrm,
                2 => Rate::Supplied(*rate),
                _ => return None,
            };
            return Some(
                match math::project::<FAST>(m, now.as_u128()?.try_into().ok()?, rate) {
                    None => "UNKNOWN".into(),
                    Some(p) => format!(
                        "OK {}",
                        [
                            p.market.supply_assets,
                            p.market.supply_shares,
                            p.market.borrow_assets,
                            p.market.borrow_shares,
                            p.market.last_update_s as u128,
                            p.market.fee,
                            p.interest,
                            p.fee_shares
                        ]
                        .iter()
                        .map(|x| U256::from(*x).hex())
                        .collect::<Vec<_>>()
                        .join(" ")
                    ),
                },
            );
        }
        _ => return None,
    };
    Some(match result {
        Ok(v) => format!(
            "OK {}",
            v.iter().map(|x| x.hex()).collect::<Vec<_>>().join(" ")
        ),
        Err(e) => format!("ERR {}", e as u8),
    })
}
fn main() {
    let reference = std::env::args().any(|x| x == "--reference");
    for line in io::stdin().lock().lines() {
        println!(
            "{}",
            line.ok()
                .and_then(|s| if reference {
                    eval::<false>(&s)
                } else {
                    eval::<true>(&s)
                })
                .unwrap_or("PARSE_ERROR".into())
        );
    }
}
