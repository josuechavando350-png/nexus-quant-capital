//! Artifact-only transport. Built as an example in an expendable source copy.
//! No streams, checkpoints, range certificates, RPC or signing are created.
use nqc_census_store::verify::{verify_store, VerifyRequest};
use nqc_census_store::{ArtifactId, Store, StoreConfig};
use std::error::Error;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

const MAX_FILES: usize = 257;
const MAX_BYTES: u64 = 64 * 1024 * 1024;
type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn safe(path: &Path) -> Result<()> {
    if !path.is_absolute() { return Err("absolute path required".into()); }
    for part in path.ancestors() {
        if part.components().any(|c| c == std::path::Component::ParentDir) {
            return Err("parent traversal".into());
        }
        match fs::symlink_metadata(part) {
            Ok(m) if m.file_type().is_symlink() => return Err("symlink path".into()),
            Ok(_) => (),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}

fn input(path: &Path) -> Result<Vec<(ArtifactId, Vec<u8>)>> {
    safe(path)?;
    let mut rows = Vec::new();
    let mut total = 0_u64;
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        if !entry.file_type()?.is_file() { return Err("nonregular input".into()); }
        let name = entry.file_name().into_string().map_err(|_| "nonutf8 name")?;
        let id = ArtifactId::parse_hex(&name)?;
        let mut bytes = Vec::new();
        fs::File::open(entry.path())?.take(MAX_BYTES + 1).read_to_end(&mut bytes)?;
        total += u64::try_from(bytes.len())?;
        if bytes.is_empty() || total > MAX_BYTES || rows.len() >= MAX_FILES {
            return Err("transport bounds".into());
        }
        if ArtifactId::of(&bytes) != id { return Err("input digest mismatch".into()); }
        rows.push((id, bytes));
    }
    if rows.is_empty() { return Err("empty input".into()); }
    rows.sort_by_key(|r| r.0);
    Ok(rows)
}

fn checked(store: &Path) -> Result<nqc_census_store::verify::VerifyReport> {
    safe(store)?;
    let report = verify_store(store, &VerifyRequest::default())?;
    if !report.streams.is_empty() || report.artifacts == 0
        || report.artifacts > MAX_FILES as u64 || report.logical_bytes > MAX_BYTES
        || report.orphan_artifacts != report.artifacts || report.orphan_chunks != 0
        || report.staging_files != 0 || report.abandoned_registrations != 0 {
        return Err("not a complete artifact-only transport".into());
    }
    Ok(report)
}

fn import(source: &Path, destination: &Path) -> Result<()> {
    // Validate everything before opening a destination. An interrupted import
    // is not a checkpoint and must not be treated as a complete replica.
    let rows = input(source)?;
    safe(destination)?;
    if destination.exists() { return Err("destination exists".into()); }
    let store = Store::create(destination, StoreConfig::standard())?;
    for (expected, bytes) in &rows {
        let put = store.put_artifact(bytes)?;
        if put.id != *expected || store.get_artifact(expected)? != *bytes
            || store.verify_artifact(expected)? != bytes.len() as u64 {
            return Err("roundtrip mismatch".into());
        }
        let retry = store.put_artifact(bytes)?;
        if retry.id != *expected || retry.manifest_created || retry.chunks_created != 0 {
            return Err("nonidempotent object retry".into());
        }
    }
    if checked(destination)?.artifacts != rows.len() as u64 {
        return Err("inventory count mismatch".into());
    }
    Ok(())
}

fn export(source: &Path, destination: &Path) -> Result<()> {
    let report = checked(source)?;
    let store = Store::open_existing(source)?;
    safe(destination)?;
    if destination.exists() { return Err("destination exists".into()); }
    fs::create_dir(destination)?;
    let mut count = 0_u64;
    for fan in fs::read_dir(source.join("objects/artifacts"))? {
        for entry in fs::read_dir(fan?.path())? {
            let entry = entry?;
            let name = entry.file_name().into_string().map_err(|_| "nonutf8 name")?;
            let id = ArtifactId::parse_hex(&name)?;
            let bytes = store.get_artifact(&id)?;
            let mut file = OpenOptions::new().write(true).create_new(true)
                .open(destination.join(id.to_hex()))?;
            file.write_all(&bytes)?;
            file.sync_all()?;
            count += 1;
        }
    }
    if count != report.artifacts { return Err("export count mismatch".into()); }
    fs::File::open(destination)?.sync_all()?;
    Ok(())
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() != 3 { return Err("usage: bridge import|export SOURCE DESTINATION".into()); }
    let source = PathBuf::from(&args[1]);
    let destination = PathBuf::from(&args[2]);
    match args[0].as_str() {
        "import" => import(&source, &destination)?,
        "export" => export(&source, &destination)?,
        _ => return Err("unknown operation".into()),
    }
    println!("OMEGA_RUST_TRANSPORT=PASS");
    Ok(())
}
