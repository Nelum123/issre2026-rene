### Rules

- Once a prompt begins, you are free to create files and folders as you wish, but you can only remove files created during the prompt. If this rule is followed, you don't need to ask me for permission to remove files.
- Example for the pipeline is located in `esem2026-dependencies/`, but note that it is not complete, meaning some features are missing.

### Definitions

- The goal of this project is to make a custom parser with required attributes.
- The pipeline is as follows:
  1. Specifify attributes stored in a JSON file (refered to as the source input file).
  2. Convert the attributes into generator parameters using a converter.
  3. From the parameters, create an LL(1) context-free grammar using a grammar generator.
  4. From the grammar and the source input file, convert into a parser using a parser generator.