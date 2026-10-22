# Prepared pin; Nix evaluation/build has NOT been run in this environment.
# No flake.lock with an invented narHash is supplied. fetchGit uses the exact
# official nixpkgs commit; Cargo.lock supplies registry package checksums.
let
  nixpkgsSource = builtins.fetchGit {
    url = "https://github.com/NixOS/nixpkgs";
    rev = "0b0c249f090b05e3a47dcdd523c54921e5223409";
    shallow = true;
  };
  pkgs = import nixpkgsSource { };
in
assert pkgs.rustc.version == "1.90.0";
pkgs.rustPlatform.buildRustPackage {
  pname = "nqc-miner";
  version = "0.1.0";
  src = pkgs.lib.cleanSourceWith {
    src = ../.;
    filter = path: type:
      let
        relative = pkgs.lib.removePrefix (toString ../. + "/") (toString path);
      in
        relative == "Cargo.toml" || relative == "Cargo.lock" || relative == "build.rs"
        || relative == "src" || pkgs.lib.hasPrefix "src/" relative
        || relative == "tests" || pkgs.lib.hasPrefix "tests/" relative;
  };
  cargoLock.lockFile = ../Cargo.lock;
  doCheck = true;
  strictDeps = true;
  # A source-only Nix input has no Git checkout. build.rs therefore deliberately
  # reports commit=unknown / source_dirty=true; read-only scan's source identity
  # gate refuses it. Offline verification/replay remains available. A separately
  # reviewed, cryptographically bound source attestation is needed for a scan-
  # capable hermetic release; this file does not bypass that gate.
  meta = {
    description = "Isolated NQC Miner offline research and verification binary";
    platforms = pkgs.lib.platforms.linux;
    mainProgram = "nqc-miner";
  };
}
