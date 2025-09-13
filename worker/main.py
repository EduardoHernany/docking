import os
from pathlib import Path
from time import sleep

MOLECULES_DIR = Path(os.getenv("MOLECULES_DIR", "/app/files/molecules"))

def main():
    print(f"[worker] rodando. observando {MOLECULES_DIR}")
    MOLECULES_DIR.mkdir(parents=True, exist_ok=True)

    # placeholder: lista diretórios e fica vivo
    try:
        while True:
            try:
                items = sorted(MOLECULES_DIR.glob("*"))
                print(f"[worker] itens: {[p.name for p in items]}")
            except Exception as e:
                print(f"[worker] erro listando: {e}")
            sleep(10)
    except KeyboardInterrupt:
        print("[worker] encerrando.")

if __name__ == "__main__":
    main()
