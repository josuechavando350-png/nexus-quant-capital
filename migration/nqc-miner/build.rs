use sha2::{Digest, Sha256};
use std::{
    env, fs,
    path::{Path, PathBuf},
    process::Command,
};

fn git(root: &Path, args: &[&str]) -> Option<String> {
    let output = Command::new("git")
        .current_dir(root)
        .args(args)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    Some(String::from_utf8(output.stdout).ok()?.trim().to_owned())
}
fn command(program: &str, args: &[&str]) -> Option<String> {
    let output = Command::new(program).args(args).output().ok()?;
    if !output.status.success() {
        return None;
    }
    Some(String::from_utf8(output.stdout).ok()?.trim().to_owned())
}
fn sources(directory: &Path, files: &mut Vec<PathBuf>) {
    for entry in fs::read_dir(directory).expect("source directory") {
        let path = entry.expect("source entry").path();
        if path.is_dir() {
            sources(&path, files);
        } else if path.extension().is_some_and(|e| e == "rs") {
            files.push(path);
        }
    }
}
fn main() {
    let root = PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("manifest dir"));
    let commit = git(&root, &["rev-parse", "HEAD"]).unwrap_or_else(|| "unknown".into());
    let dirty = git(
        &root,
        &[
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            "src",
            "Cargo.toml",
            "Cargo.lock",
            "build.rs",
            "rust-toolchain.toml",
        ],
    )
    .is_none_or(|s| !s.is_empty());
    let lock = fs::read(root.join("Cargo.lock")).expect("Cargo.lock must be committed");
    let rustc = env::var("RUSTC").unwrap_or_else(|_| "rustc".into());
    let rustc_version = command(&rustc, &["--version"]).unwrap_or_else(|| "unknown".into());
    let target = env::var("TARGET").unwrap_or_else(|_| "unknown".into());
    let host = env::var("HOST").unwrap_or_else(|_| "unknown".into());
    let profile = env::var("PROFILE").unwrap_or_else(|_| "unknown".into());
    let opt_level = env::var("OPT_LEVEL").unwrap_or_else(|_| "unknown".into());
    let debug = env::var("DEBUG").unwrap_or_else(|_| "unknown".into());
    let rustflags = env::var("CARGO_ENCODED_RUSTFLAGS").unwrap_or_default();
    let mut files = vec![
        root.join("Cargo.toml"),
        root.join("Cargo.lock"),
        root.join("build.rs"),
        root.join("rust-toolchain.toml"),
    ];
    sources(&root.join("src"), &mut files);
    files.sort();
    let mut hasher = Sha256::new();
    for path in files {
        hasher.update(
            path.strip_prefix(&root)
                .expect("relative source")
                .to_string_lossy()
                .as_bytes(),
        );
        hasher.update([0]);
        hasher.update(fs::read(path).expect("source bytes"));
        hasher.update([0]);
    }
    println!("cargo:rustc-env=NQC_MINER_BUILD_COMMIT={commit}");
    println!("cargo:rustc-env=NQC_MINER_BUILD_DIRTY={dirty}");
    println!(
        "cargo:rustc-env=NQC_MINER_BUILD_LOCK_SHA256={:x}",
        Sha256::digest(lock)
    );
    println!(
        "cargo:rustc-env=NQC_MINER_BUILD_SOURCE_SHA256={:x}",
        hasher.finalize()
    );
    println!("cargo:rustc-env=NQC_MINER_BUILD_RUSTC_VERSION={rustc_version}");
    println!("cargo:rustc-env=NQC_MINER_BUILD_TARGET={target}");
    println!("cargo:rustc-env=NQC_MINER_BUILD_HOST={host}");
    println!("cargo:rustc-env=NQC_MINER_BUILD_PROFILE={profile}");
    println!("cargo:rustc-env=NQC_MINER_BUILD_OPT_LEVEL={opt_level}");
    println!("cargo:rustc-env=NQC_MINER_BUILD_DEBUG={debug}");
    println!(
        "cargo:rustc-env=NQC_MINER_BUILD_RUSTFLAGS_SHA256={:x}",
        Sha256::digest(rustflags.as_bytes())
    );
    println!("cargo:rerun-if-changed=src");
    println!("cargo:rerun-if-changed=Cargo.toml");
    println!("cargo:rerun-if-changed=Cargo.lock");
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=rust-toolchain.toml");
    println!("cargo:rerun-if-changed=../../.git/HEAD");
    println!("cargo:rerun-if-changed=../../.git/index");
    if let Some(head) = git(&root, &["symbolic-ref", "--quiet", "HEAD"]) {
        println!("cargo:rerun-if-changed=../../.git/{head}");
    }
}
