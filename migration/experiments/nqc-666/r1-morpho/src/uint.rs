//! Checked 256-bit arithmetic. No floating point, unchecked truncation or external crate.
use core::cmp::Ordering;

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct U256(pub [u64; 4]);
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Arithmetic {
    Overflow = 17,
    DivisionByZero = 18,
}
impl Ord for U256 {
    fn cmp(&self, rhs: &Self) -> Ordering {
        self.0.iter().rev().cmp(rhs.0.iter().rev())
    }
}
impl PartialOrd for U256 {
    fn partial_cmp(&self, rhs: &Self) -> Option<Ordering> {
        Some(self.cmp(rhs))
    }
}
impl From<u128> for U256 {
    fn from(v: u128) -> Self {
        Self([v as u64, (v >> 64) as u64, 0, 0])
    }
}
impl U256 {
    pub const ZERO: Self = Self([0; 4]);
    pub const MAX: Self = Self([u64::MAX; 4]);
    pub fn as_u128(self) -> Option<u128> {
        (self.0[2] == 0 && self.0[3] == 0)
            .then_some(self.0[0] as u128 | ((self.0[1] as u128) << 64))
    }
    pub fn checked_add(self, rhs: Self) -> Result<Self, Arithmetic> {
        let mut out = [0; 4];
        let mut carry = false;
        for (i, slot) in out.iter_mut().enumerate() {
            let (v, c1) = self.0[i].overflowing_add(rhs.0[i]);
            let (v, c2) = v.overflowing_add(u64::from(carry));
            *slot = v;
            carry = c1 || c2;
        }
        if carry {
            Err(Arithmetic::Overflow)
        } else {
            Ok(Self(out))
        }
    }
    pub fn checked_sub(self, rhs: Self) -> Result<Self, Arithmetic> {
        let mut out = [0; 4];
        let mut borrow = false;
        for (i, slot) in out.iter_mut().enumerate() {
            let (v, b1) = self.0[i].overflowing_sub(rhs.0[i]);
            let (v, b2) = v.overflowing_sub(u64::from(borrow));
            *slot = v;
            borrow = b1 || b2;
        }
        if borrow {
            Err(Arithmetic::Overflow)
        } else {
            Ok(Self(out))
        }
    }
    pub fn checked_mul<const FAST: bool>(self, rhs: Self) -> Result<Self, Arithmetic> {
        if FAST {
            if let (Some(a), Some(b)) = (self.as_u128(), rhs.as_u128()) {
                if let Some(v) = a.checked_mul(b) {
                    return Ok(v.into());
                }
            }
        }
        let mut wide = [0u64; 8];
        for i in 0..4 {
            let mut carry = 0u128;
            for j in 0..4 {
                let v = self.0[i] as u128 * rhs.0[j] as u128 + wide[i + j] as u128 + carry;
                wide[i + j] = v as u64;
                carry = v >> 64;
            }
            wide[i + 4] = carry as u64;
        }
        if wide[4..].iter().any(|x| *x != 0) {
            return Err(Arithmetic::Overflow);
        }
        Ok(Self([wide[0], wide[1], wide[2], wide[3]]))
    }
    fn bits(self) -> u32 {
        for i in (0..4).rev() {
            if self.0[i] != 0 {
                return i as u32 * 64 + 64 - self.0[i].leading_zeros();
            }
        }
        0
    }
    fn shifted(self, n: u32) -> Self {
        let mut out = [0; 4];
        let words = n as usize / 64;
        let bits = n % 64;
        for (i, slot) in out.iter_mut().enumerate().skip(words) {
            *slot = self.0[i - words] << bits;
            if bits != 0 && i > words {
                *slot |= self.0[i - words - 1] >> (64 - bits);
            }
        }
        Self(out)
    }
    fn half(self) -> Self {
        Self([
            self.0[0] >> 1 | self.0[1] << 63,
            self.0[1] >> 1 | self.0[2] << 63,
            self.0[2] >> 1 | self.0[3] << 63,
            self.0[3] >> 1,
        ])
    }
    fn div_small(self, d: u64) -> Self {
        debug_assert!(d != 0);
        let mut out = [0; 4];
        let mut r = 0u128;
        for i in (0..4).rev() {
            let n = (r << 64) | self.0[i] as u128;
            out[i] = (n / d as u128) as u64;
            r = n % d as u128;
        }
        Self(out)
    }
    pub fn checked_div<const FAST: bool>(self, d: Self) -> Result<Self, Arithmetic> {
        if d == Self::ZERO {
            return Err(Arithmetic::DivisionByZero);
        }
        if FAST {
            if let (Some(n), Some(d)) = (self.as_u128(), d.as_u128()) {
                return Ok((n / d).into());
            }
            if d.0[1..] == [0, 0, 0] {
                return Ok(self.div_small(d.0[0]));
            }
            // floor(floor(n / WAD) / WAD) == floor(n / WAD^2), exactly.
            if d == Self::from(10u128.pow(36)) {
                return Ok(self.div_small(10u64.pow(18)).div_small(10u64.pow(18)));
            }
        }
        if self < d {
            return Ok(Self::ZERO);
        }
        let shift = self.bits() - d.bits();
        let mut divisor = d.shifted(shift);
        let mut rem = self;
        let mut q = Self::ZERO;
        for bit in (0..=shift).rev() {
            if rem >= divisor {
                rem = rem.checked_sub(divisor)?;
                q.0[bit as usize / 64] |= 1u64 << (bit % 64);
            }
            divisor = divisor.half();
        }
        Ok(q)
    }
    pub fn from_hex(text: &str) -> Option<Self> {
        let text = text.strip_prefix("0x").unwrap_or(text);
        if text.is_empty() || text.len() > 64 || !text.bytes().all(|c| c.is_ascii_hexdigit()) {
            return None;
        }
        let mut out = [0; 4];
        for (i, chunk) in text.as_bytes().rchunks(16).enumerate() {
            out[i] = u64::from_str_radix(core::str::from_utf8(chunk).ok()?, 16).ok()?;
        }
        Some(Self(out))
    }
    pub fn hex(self) -> String {
        format!(
            "{:016x}{:016x}{:016x}{:016x}",
            self.0[3], self.0[2], self.0[1], self.0[0]
        )
    }
}
