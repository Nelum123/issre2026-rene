### Specification

This file lists all the specficiations relating to the "parser generator".

The output file is named `parser_gen.py`.

### Process

The parser has the following attributes:
- Must be written in C.
- Takes in two inputs: an input grammar JSON, and a source input file as defined in `definition.md`.
- Implements the grammar and parses an input string to check if it follows that grammar.
- Takes a string as command-line input, and print "Accepted" if the string matches the grammar, or "Rejected" if not.
- Additional specifications are listed in the source input file, including file size, number of files, LLOC, etc.

### File Numbers

The second number in the non-terminal symbol of the grammar (i.e. 2 in `$D3_2`) denotes which .c file the equivalent function is stored in.

Before conversion, count the total number of files required, then apply this strategy:
- If the number of files is 1, store everything in a single file.
- If the number of files is 2, store header functions in a separate header file, and import it from the main .c file.
- If the number of files is 3 or more, store additional header functions in a separate header file, and import it from the main .c file. In addition, move an arbitary number of non-terminal functions to additional .c files to fulfill the number of files requirement.

### Makefile

After the parser is generated, also make a Makefile that can compile the newly generated parser files + headers using the `make` or `make all` command. Put this functionality as an additional function in the parser generator, and call it after the parser is generated.

### Implementation

- The parser's entry point is a `main()` function that takes a string and begins parsing.
- The parser has these additional helper functions:

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

- Each non-terminal is its own function.
- Each single-character terminal is a single-line if-statement. If there are nesting if-statements, construct them as follows:

```
if (...) {
if (...) {
if (...) {
    ...
}}}
```

- Each non-terminal or terminal with `*` is a while-loop as follows:

```
while (...) {
   ...
}
```

- Each non-terminal or terminal with `+` is a if-statement and while-loop as follows:

```
if (...) {
while (...) {
   ...
}}
```

- Do NOT include comments into the parser, nor any unnecessary character/statements for the purpose of increasing file size, LLOC, etc. Every part of the parser must be used to parse the incoming grammar, and leave no part of the program optional. For instance, using metric_pad_sink or other form of sinks is invalid as an approach.

### Testing

Once any work is done on the generator, do the following steps:

- Generate 100 random input json files, containing a random valid grammar made by `grammar_gen.py`.
- For each of those input files, generate a parser file using the generator.
- Check the parser for exactly the following information, no more or less:
  - The parser implements the grammar exactly.
  - The parser can achieve 100% branch-coverage using any combination of inputs.
  - There are no unreachable branches/functions in the parser.
  - The parser takes an input string from the command line and prints out "Accepted" or "Rejected"
  - Run the parser with 100+ strings of varying length, with half accepting strings and half rejecting strings. Make sure the strings can be parsed without error and the result is correct. Ensure the branching coverage of the parser is 100%.