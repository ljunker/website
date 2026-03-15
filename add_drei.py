import subprocess
import sys

def parse_numbers(num_str):
    return [int(num.strip()) for num in num_str.split(",")]

NUMBER_FILE = "drei-fragezeichen-collected.txt"

def backup_file():
    try:
        with open(NUMBER_FILE, "r") as original_file:
            with open(f"{NUMBER_FILE}.bak", "w") as backup_file:
                backup_file.write(original_file.read())
    except FileNotFoundError:
        # If the original file doesn't exist, we can ignore the backup step
        pass
    except IOError as e:
        print(f"ERROR: Failed to create backup: {e}")
        raise

def restore_backup():
    try:
        with open(f"{NUMBER_FILE}.bak", "r") as backup_file:
            with open(NUMBER_FILE, "w") as original_file:
                original_file.write(backup_file.read())
    except FileNotFoundError:
        print("ERROR: Backup file not found. Cannot restore.")
    except IOError as e:
        print(f"ERROR: Failed to restore from backup: {e}")
        raise

def delete_backup():
    try:
        import os
        os.remove(f"{NUMBER_FILE}.bak")
    except FileNotFoundError:
        # If the backup file doesn't exist, we can ignore the delete step
        pass
    except IOError as e:
        print(f"ERROR: Failed to delete backup: {e}")
        raise

def insert_to_file(new_numbers: list) -> int|None:
    numbers = []
    changes = 0
    # check if the file exists, if not create it
    try:
        open(NUMBER_FILE, "r").close()
    except FileNotFoundError:
        open(NUMBER_FILE, "w").close()

    backup_file()

    with open(NUMBER_FILE, "r") as file:
        numbers = [int(line.strip()) for line in file]
        for new_number in new_numbers:
            if new_number in numbers:
                print(f"INFO: Number {new_number} already exists in the file.")
            else:
                numbers.append(new_number)
                changes += 1
        # sort lines in the file
        numbers.sort()
    with open(NUMBER_FILE, "w") as file:
        try:
            for num in numbers:
                file.write(f"{num}\n")
        except IOError as e:
            print(f"ERROR: Failed to write to file: {e}")
            restore_backup()
            raise

    delete_backup()
    return changes

def git_commit_and_push():
    import subprocess
    try:
        subprocess.run(["git", "add", NUMBER_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Add new numbers to the file"], check=True)
        subprocess.run(["git", "push"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Git operation failed: {e}")
        raise


def main(args) -> int:
    try:
        changes = insert_to_file(parse_numbers(args))
        if changes is not None and changes > 0:
            git_commit_and_push()
    except ValueError:
        print(f"ERROR: '{args}' contains invalid number(s).")
        return 1
    except IOError as e:
        print(f"ERROR: File operation failed: {e}")
        return 1
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Git operation failed: {e}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))