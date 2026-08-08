#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

const DEFAULT_PORT: u16 = 8765;

fn port_open(port: u16) -> bool {
    TcpStream::connect(("127.0.0.1", port)).is_ok()
}

fn main() {
    let port = std::env::var("MYOPENCODE_PORT")
        .ok()
        .and_then(|p| p.parse::<u16>().ok())
        .unwrap_or(DEFAULT_PORT);

    if !port_open(port) {
        let python = std::env::var("MYOPENCODE_PYTHON").unwrap_or_else(|_| "python".into());
        let cwd = std::env::current_dir().unwrap_or_default();
        thread::spawn(move || {
            let _ = Command::new(python)
                .args(["-X", "utf8", "agent.py"])
                .current_dir(&cwd)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn();
            for _ in 0..240 {
                if port_open(port) {
                    break;
                }
                thread::sleep(Duration::from_millis(500));
            }
        });
    }

    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
