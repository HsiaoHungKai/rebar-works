import os
import sys


def rename_files_remove_copy_suffix(folder_path):
    """
    Rename files by removing ' 的副本' suffix from filenames
    Example: '20250502_145328.jpg 的副本.jpg' -> '20250502_145328.jpg'
    """
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return

    renamed_count = 0

    # Get all files in the folder
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)

        # Skip directories
        if os.path.isdir(file_path):
            continue

        # Check if filename contains ' 的副本'
        if ".jpg 的副本.jpg" in filename:
            # Remove ' 的副本' from the filename
            new_filename = filename.replace(".jpg 的副本.jpg", ".jpg")
            new_file_path = os.path.join(folder_path, new_filename)

            # Check if target file already exists
            if os.path.exists(new_file_path):
                print(
                    f"Warning: Target file '{new_filename}' already exists. Skipping '{filename}'"
                )
                continue

            try:
                # Rename the file
                os.rename(file_path, new_file_path)
                print(f"Renamed: '{filename}' -> '{new_filename}'")
                renamed_count += 1
            except OSError as e:
                print(f"Error renaming '{filename}': {e}")

    print(f"\nTotal files renamed: {renamed_count}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python rename.py <folder_path>")
        print("Example: python rename.py ./images")
        return

    folder_path = sys.argv[1]

    # Convert relative path to absolute path
    folder_path = os.path.abspath(folder_path)

    print(f"Processing folder: {folder_path}")

    # Ask for confirmation
    response = input("Do you want to proceed with renaming files? (y/N): ")
    if response.lower() != "y":
        print("Operation cancelled.")
        return

    rename_files_remove_copy_suffix(folder_path)


if __name__ == "__main__":
    main()
