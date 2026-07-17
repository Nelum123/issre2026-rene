### Before Testing

If it doesn't exist, generate a folder named `test-cases/` and include in there 200 test cases folder. In each folder, include an `input.json` file that contains the input to the beginning of the pipeline. This folder and its contents are not to be changed once made.

These input files contains a wide range of combinations of possible inputs, including all possible values and missing values. The following ranges (including min and max values, and any value in between) are mandatory in the test cases:
  - LLOC: 100 - 50000.
  - File Count: 1 - 100.
  - File size: 1 - 20000
  - Block count: 10 - 50000
  - MRD: 1 - 100
  - Max Depth: 1 - 20
  - CC: 10 - 5000
  - n_1: 10 - 500
  - n_2: 10 - 500
  - N_1: 10 - 500
  - N_2: 10 - 500
  - HVoc: 50 - 10000
  - HLen: 300 - 200000
  - HVol: 1600 - 10000000
  - HDif: 30 - 90000

### During Testing

Test the entire pipeline as follows:

1. Copy all the test cases from `test-cases/` to a separate temporary testing folder.
2. Runs the pipeline start to finish, storing all outputs in a file for each test case.
3. Check the conditions of each component based on their respective context MD file, plus the following:
   - Compile all the parser .c files into CFGs, then calculate its MRD and Max Depth. If these two statistics are specified in the input, make sure the parser's attributes matches these values. Use `extra/build.sh` and `extra/calculate_mrd.py` for these calculations.
4. Store all the test cases, each in its own folder.

You may create or remove files that you created freely without asking me.