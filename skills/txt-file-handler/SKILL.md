---
name: txt-file-handler
description: Handle text file (.txt) operations including reading, writing, editing, and listing. Use when user needs to: (1) Read contents of a txt file, (2) Create or write to a txt file, (3) Edit or modify existing txt file content, (4) List txt files in a directory, (5) Search within txt files, (6) Append content to txt files, or any other text file manipulation tasks.
type: custom
created: 2026-04-15T17:48:02.711185
---

# TXT File Handler

## Overview

This skill provides specialized handling for plain text (.txt) file operations. While Claude has built-in tools for document operations, this skill adds best practices, common patterns, and helpful utilities specifically for text files.

## When to Use

Use this skill when working with .txt files for:
- Reading and displaying text file contents
- Creating new text files
- Modifying existing text files
- Appending content to files
- Listing text files in directories
- Searching within text files
- Formatting text output

## Core Operations

### Reading Text Files

Use `read_document` tool with the file path:

```
read_document(path="path/to/file.txt")
```

**Best practices:**
- Use `limit` parameter for very large files to avoid overwhelming output
- Text files are typically UTF-8 encoded
- For log files or structured text, consider reading in chunks

### Writing Text Files

Use `write_document` tool:

```
write_document(path="path/to/file.txt", content="Your text content here")
```

**Best practices:**
- Creates parent directories automatically if they don't exist
- Overwrites existing files completely
- Use for creating new files or replacing entire content

### Editing Text Files

Use `edit_document` tool for targeted replacements:

```
edit_document(
    path="path/to/file.txt",
    old_text="text to find",
    new_text="replacement text"
)
```

**Best practices:**
- Only replaces the first occurrence
- For multiple replacements, call edit_document multiple times
- Use exact text matching (case-sensitive)

### Listing Text Files

Use `list_documents` tool:

```
list_documents(path="directory/path")
```

**Best practices:**
- Lists all document files including .txt
- Shows last-modified timestamps
- Use to discover files before reading

## Common Patterns

### Appending to a File

Since there's no direct append tool, use read + write:

1. Read existing content
2. Append new content in memory
3. Write back combined content

### Searching Within Files

1. Read the file content
2. Use Python or string operations to search
3. Report findings with line numbers if helpful

### Processing Multiple Files

1. List files in directory
2. Filter for .txt extension
3. Process each file in sequence

## Error Handling

Common issues and solutions:

- **File not found**: Check path spelling and directory structure
- **Permission denied**: Verify file is not locked by another process
- **Encoding issues**: Text files should be UTF-8; if reading fails, file may have different encoding
- **Large files**: Use `limit` parameter to read portions at a time

## Output Formatting

When displaying text file contents:
- Preserve original formatting when possible
- Use code blocks for structured content
- Summarize very long content with key highlights
- Show line numbers when referencing specific locations
