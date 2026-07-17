# Custom Parser Pipeline

This project generates a custom C parser from requested parser attributes.

The project specification is stored in `context/`. The implementation follows this pipeline:

1. Write a source input JSON file containing requested parser attributes.
2. Run `converter.py` to convert those attributes into grammar-generation parameters.
3. Run `grammar_gen.py` to generate an LL(1) context-free grammar JSON.
4. Run `parser_gen.py` to generate C parser source files and a `Makefile`.
5. Compile, run, and verify the generated parser.


## Requirements

- Python 3
- GCC
- `make`, optional but recommended for generated parser builds
- `gcov`, if branch coverage is being measured
- GCC CFG dump support, if MRD and Max Depth are being measured

## Source Input

The source input file is a JSON object containing requested parser attributes.

Supported attributes include:

- `lloc`: logical lines of code, excluding empty lines
- `file_size`: total parser binary file size in KB
- `file_count`: number of generated parser files, defaulting to `1`
- `block_count`: number of basic blocks
- `mrd`: mean reachability depth
- `max_depth`: maximum reachability depth
- `cyclomatic_complexity` or `cc`
- Halstead metrics:
  - `halstead_n1` or `n_1`: distinct operators
  - `halstead_n2` or `n_2`: distinct operands
  - `halstead_N1` or `N_1`: total operator occurrences
  - `halstead_N2` or `N_2`: total operand occurrences
  - `halstead_vocabulary` or `hvoc`
  - `halstead_length` or `hlen`
  - `halstead_volume` or `hvol`
  - `halstead_difficulty` or `hdif`

Example:

```json
{
  "file_count": 2,
  "lloc": 120
}
```

`file_count` may be combined with any other supported attribute. Apart from `file_count`, only one target attribute may be specified at a time. For example, `{"file_count": 3, "lloc": 500}` is valid, while `{"lloc": 500, "mrd": 4}` is invalid.

If an attribute is below the minimum parser produced from the minimum grammar, the converter treats it as the minimum value. The minimum grammar is:

```json
{
  "$start": [["a"]]
}
```

## Converter

`converter.py` reads the source input JSON and writes the grammar parameters used by the grammar generator.

Command:

```bash
python converter.py input.json -o converter_output.json --seed 123
```

Output fields:

```json
{
  "nts_per_depth": 1,
  "rules_per_def": 2,
  "rule_len": 3,
  "nt_per_rule": 1,
  "star_count": 0,
  "plus_count": 1
}
```

The converter output always contains all six grammar parameters:

- `nts_per_depth`: number of nonterminals per depth
- `rules_per_def`: number of rules per definition
- `rule_len`: length of each rule
- `nt_per_rule`: number of nonterminals per rule
- `star_count`: total number of `*` suffixes in the grammar
- `plus_count`: total number of `+` suffixes in the grammar

Specified inputs map deterministically to affected output fields. Unspecified fields may be arbitrary; `--seed` makes those choices repeatable.

Invalid inputs cause `converter.py` to exit with an error. Inputs are invalid when conflicting target attributes are specified together, or when `file_count` is higher than the number of parser functions that can be generated.

## Grammar Generator

`grammar_gen.py` reads the converter output and generates an LL(1) grammar.

Command:

```bash
python grammar_gen.py converter_output.json -o grammar.json --seed 456
```

Example grammar:

```json
{
  "$start": [["a", "$D1+"]],
  "$D1": [["a"]]
}
```

Grammar rules:

- Terminals are lowercase characters from `a-z`.
- Nonterminals are named `$D1`, `$D2`, etc.
- `*` means zero or more occurrences.
- `+` means one or more occurrences.
- `*` and `+` may only be placed after nonterminals, not terminals.
- A single production must not contain multiple copies of the same nonterminal, with or without a suffix.
- Generated grammars must be LL(1).
- Generated grammars must not contain unreachable nonterminals.
- Grammar statistics must match the converter output exactly.

The minimum output grammar is:

```json
{
  "$start": [["a"]]
}
```

## Parser Generator

`parser_gen.py` reads a grammar JSON file and the original source input file, then generates a C parser.

Command:

```bash
python parser_gen.py grammar.json input.json -o generated_parser
```

You can also override the emitted file count directly:

```bash
python parser_gen.py grammar.json input.json -o generated_parser --file-count 3
```

The generated parser:

- is written in C
- implements the grammar exactly
- reads the candidate input string from the command line
- prints `Accepted` if the string matches the grammar
- prints `Rejected` otherwise
- emits a `Makefile` that supports `make` and `make all`

Generated output may contain:

- `parser.c`
- additional `.c` files, depending on `file_count`
- `parser_helpers.h`, when helper declarations are split out
- `Makefile`

File splitting follows the parser specification:

- `file_count = 1`: store everything in one C file.
- `file_count = 2`: store helper functions in a separate header and import it from the main C file.
- `file_count >= 3`: store helper functions in a header, then move nonterminal functions into additional C files until the file-count requirement is met.

Build:

```bash
cd generated_parser
make all
```

If `make` is unavailable, compile with GCC directly:

```bash
gcc -O0 *.c -o parser.exe
```

Run:

```bash
./parser.exe "input string"
```

The parser prints:

```text
Accepted
```

or:

```text
Rejected
```

The generated parser includes the required helper functions:

```c
static char peek(void) {
    while (input[pos]==' '||input[pos]=='\t') pos++;
    return input[pos];
}

static int match_char(char c) {
    if (peek() == c) { pos++; return 1; }
    return 0;
}
```

Each nonterminal is emitted as its own function. Parser code must not contain comments, unused padding, optional metric sinks, or unreachable branches/functions.

## Verifiers

Independent verifiers live in `verifiers/`:

- `verifiers/converter_verifier.py`
- `verifiers/grammar_gen_verifier.py`
- `verifiers/parser_gen_verifier.py`
- `verifiers/pipeline_verifier.py`
- `verifiers/mrd_verifier.py`

Examples:

```bash
python verifiers/converter_verifier.py input.json converter_output.json
python verifiers/grammar_gen_verifier.py converter_output.json grammar.json
python verifiers/parser_gen_verifier.py input.json generated_parser
python verifiers/pipeline_verifier.py input.json generated_parser
python verifiers/mrd_verifier.py generated_parser --entry main
```

`pipeline_verifier.py` calculates final parser statistics and compares specified source-input values against the generated parser. Specified values pass when they fall within the accepted 5% error margin.

Use `--no-mrd` to skip CFG-based MRD and Max Depth calculation:

```bash
python verifiers/pipeline_verifier.py input.json generated_parser --no-mrd
```

## MRD and Max Depth

MRD and Max Depth are calculated from GCC CFG dumps. MRD is the sum of depths of all non-entry basic blocks divided by the number of non-entry basic blocks.

Inside a generated parser directory:

```bash
gcc -O0 -g0 -fdump-tree-cfg-graph -fdump-ipa-cgraph *.c -o mrd_test_bin
mkdir mrd_dumps
mv *.cfg *.cfg.dot *.cgraph *.ipa-cgraph mrd_dumps/
python ../../extra/calculate_mrd.py mrd_dumps --entry main --json-out mrd_dumps/mrd_output.json
```

The helper script in `extra/` can also build the required dumps:

```bash
cd generated_parser
bash ../../extra/build.sh main
python ../../extra/calculate_mrd.py mrd_dumps --entry main --json-out mrd_dumps/mrd_output.json
```

The result is written to:

```text
mrd_dumps/mrd_output.json
```

## Testing

The full pipeline test described in `context/testing.md` requires a stable `test-cases/` directory containing 200 case folders. Each case contains an `input.json`, and this directory should not be changed once created.

Mandatory source-input ranges across the test suite include:

- LLOC: `100` to `50000`
- File count: `1` to `100`
- File size: `1` to `20000`
- Block count: `10` to `50000`
- MRD: `1` to `100`
- Max Depth: `1` to `20`
- Cyclomatic complexity: `10` to `5000`
- Halstead `n_1`, `n_2`, `N_1`, `N_2`: `10` to `500`
- Halstead Vocabulary: `50` to `10000`
- Halstead Length: `300` to `200000`
- Halstead Volume: `1600` to `10000000`
- Halstead Difficulty: `30` to `90000`

During testing:

1. Copy the cases from `test-cases/` to a separate temporary testing folder.
2. Run the full pipeline for each case.
3. Verify converter, grammar generator, parser generator, and final parser outputs.
4. Compile generated parser files.
5. Run accepted and rejected parser-input strings.
6. Measure branch coverage; generated parsers must be able to reach 100% branch coverage.
7. Compile parser CFG dumps and calculate MRD and Max Depth when required.
8. Write one `report.json` for each test case.

Each `report.json` should contain only:

```json
{
  "source_input": {},
  "final_parser_statistics": {}
}
```

## Typical End-to-End Example

Create `input.json`:

```json
{
  "file_count": 1,
  "lloc": 120
}
```

Run the pipeline:

```bash
python converter.py input.json -o converter_output.json --seed 1
python grammar_gen.py converter_output.json -o grammar.json --seed 2
python parser_gen.py grammar.json input.json -o generated_parser
cd generated_parser
gcc -O0 *.c -o parser.exe
./parser.exe "a"
```

The generated parser accepts or rejects the command-line string according to the generated grammar.
