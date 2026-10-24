import os
import zipfile

def package_submission(zip_path="code.zip"):
    # Delete existing zip if present
    if os.path.exists(zip_path):
        os.remove(zip_path)

    included_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add root files
        for root_file in ["README.md", "AGENTS.md", "problem_statement.md", ".gitignore"]:
            if os.path.exists(root_file):
                zf.write(root_file, root_file)
                included_count += 1
                print(f"Added root file: {root_file}")

        # Add code directory
        for root, dirs, files in os.walk("code"):
            # Exclude __pycache__
            if "__pycache__" in root:
                continue
            for file in files:
                if file.endswith((".pyc", ".pyo", ".swp")):
                    continue
                # Do not include nested archives
                if file.endswith((".zip", ".tar", ".gz", ".tgz", ".7z", ".rar")):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, ".")
                zf.write(file_path, rel_path)
                included_count += 1

        # Also add evaluation directory if outside code
        for root, dirs, files in os.walk("evaluation"):
            if "__pycache__" in root:
                continue
            for file in files:
                if file.endswith((".pyc", ".pyo", ".zip")):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, ".")
                zf.write(file_path, rel_path)
                included_count += 1

    file_size_kb = os.path.getsize(zip_path) / 1024
    print(f"\nSuccessfully created {zip_path} with {included_count} files ({file_size_kb:.1f} KB).")

    # Verify no dataset or forbidden files in code.zip
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        for n in names:
            assert not n.startswith("dataset/"), f"FORBIDDEN: dataset file in code.zip: {n}"
            assert not ".venv" in n, f"FORBIDDEN: venv file in code.zip: {n}"
            assert not "__pycache__" in n, f"FORBIDDEN: cache file in code.zip: {n}"
            assert not n.endswith((".zip", ".tar", ".gz")), f"FORBIDDEN: nested archive in code.zip: {n}"
    print("Verification passed: code.zip strictly complies with all challenge constraints!")

if __name__ == "__main__":
    package_submission()
