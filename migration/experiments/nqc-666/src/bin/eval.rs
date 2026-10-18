use std::io::{self, BufRead};
fn main() {
    for line in io::stdin().lock().lines() {
        match line
            .map_err(|e| e.to_string())
            .and_then(|s| nqc666::financial::parse(&s))
        {
            Ok(c) => println!("{}", nqc666::financial::screen(&c).line()),
            Err(_) => println!("PARSE_ERROR"),
        }
    }
}
