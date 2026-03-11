fn main() {
    // Rebuild when embedded frontend assets change.
    println!("cargo:rerun-if-changed=web/dist");
    // Keep builtin skills embedding in sync as well.
    println!("cargo:rerun-if-changed=skills/built-in");
}
