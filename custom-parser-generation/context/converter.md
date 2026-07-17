### Specification

This file lists all the specficiations relating to the "atrributes to grammar parameters converter".

The output file is named `converter.py`.

### Converter Input

The attributes can be the following:
- Logical Lines of Code (LLOC): The sum of the numbers of logical statements in the parser file(s), excluding empty lines.
- File size: The sum of the sizes of the parser's binary file(s), in kilobytes.
- File count: The number of files making up the parser. Unlike the other fields, if this is not specified, defaults to 1.
- Block Count: The number of basic blocks in the parser file(s). A basic block is a continous sequence of statements that runs without any jump (e.g. ifs, loops, breaks).
- Mean Reachability Depth (MRD): The sum of depths of all non-entry basic blocks, divided by the number of basic blocks. The depth of a basic block is the number of conditional statements that has to be gone through to reach that block.
- Max Depth: The maximum depth of any basic block in the parser.
- Cyclomatic Complexity (CC): Number of linearly independent control-flow paths through code
- Halstead metrics, each row is treated as its own variable:

| Symbol | Meaning                              | Example                                 |
| ------ | ------------------------------------ | --------------------------------------- |
| (n_1)  | Number of **distinct operators**     | `if`, `while`, `+`, `=`, function calls |
| (n_2)  | Number of **distinct operands**      | variables, constants, identifiers       |
| (N_1)  | Total number of operator occurrences | every time an operator appears          |
| (N_2)  | Total number of operand occurrences  | every time an operand appears           |
| **Halstead Vocabulary** (HVoc) | (n = n_1 + n_2)                            | Number of unique operators and operands                   |
| **Halstead Length** (HLen)    | (N = N_1 + N_2)                            | Total number of operator and operand occurrences          |
| **Halstead Volume** (HVol)    | (V = N \log_2(n))                          | Size of the implementation in information-theoretic terms |
| **Halstead Difficulty** (HDif) | (D = \frac{n_1}{2} \times \frac{N_2}{n_2}) | How hard the program is to understand or write            |

All of these inputs may be used in all test cases, independent of what other inputs are used:

- File count

Only one of these inputs may be used at a time:

- LLOC
- Block count
- File size
- MRD
- Max Depth
- CC
- n_1
- n_2
- N_1
- N_2
- HVoc
- HLen
- HVol
- HDif

For example, valid inputs can be: (File count, LLOC), (File size, HDif), (Block count), (n_1). An empty input means the generator can create anything.

### Converter Output

The grammar parameters are all of the following:

- nts_per_depth: the number of non-terminals per depth
- rules_per_def: the number of rules per definition.
- rule_len: the length of the rules.
- nt_per_rule: the number of non-terminals per rule.
- star_count: the total number of `*` used in the grammar.
- plus_count: the total number of `+` used in the grammar.

All of these parameters must be used to be considered as valid output.

### Process

The goal of the converter is to create a 1:1 mapping between the input and the output JSON. Once the input is specified, the converter calculates the output JSON exactly (without randomness) and returns it as a JSON file. Some of the inputs can affect one another (e.g. increasing LLOC will increase file size as well), therefore if an input have these fields together, it should be counted as invalid.

Your goal as an agent is to:
- Create a 1:1 mapping between the input and the output JSON.
- For unspecified inputs, they can be any value.
- For specified inputs, their mapping to the output should be consistent without randomization.
- Have an optional seed as input.
- Produce the output JSON.
- The generator is bare minimum, meaning it does exactly what is described here without additional checks.
- If the input is invalid, throw an error.

### Throwing Errors

- From the list of inputs above, group the inputs that directly affects each other together. If two or more inputs from the same group is provided, the input is treated as invalid.
- If File Count is higher than the total number of parser functions (that is, putting one function in each file is not enough to fulfill the File Count requirement), treat that input as invalid.
- The minimum possible acceptable input is as follows:

| Statistic | file_count = 1 | file_count = 2 |
| --- | ---: | ---: |
| LLOC | 71 | 77 |
| File size KB | 1.919 | 2.045 |
| Block Count | 9 | 9 |
| Mean Reachability Depth | 2.1875 | 2.1875 |
| Max Depth | 4 | 4 |
| Cyclomatic Complexity | 9 | 9 |
| Halstead `n_1` | 12 | 12 |
| Halstead `n_2` | 42 | 47 |
| Halstead `N_1` | 82 | 83 |
| Halstead `N_2` | 196 | 211 |
| Halstead Vocabulary | 54 | 59 |
| Halstead Length | 278 | 294 |
| Halstead Volume | 1599.859 | 1729.497 |
| Halstead Difficulty | 28.0 | 26.936 |

Generated from
```json
{
  "$start": [["a"]]
}
```

If the specified values for the input is lower than these values, treat them as these values instead.

### Testing

Once a version of the converter is generated, do the following:

- Generate 100 different inputs.
- From those, generate the output JSON.
- For each output JSON, check the following:
  - All fields in the Converter Output section is filled.
  - All the fields are consistent, that is, the same specified inputs will return the same affected outputs, while the other output fields may be randomized.
- If any of the above conditions are not valid, regenerate the converter.
