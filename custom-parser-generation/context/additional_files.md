### Verifiers

Generate additional verifiers for each component in the pipeline, titled `*_verifier.py`, following the specs of each component from their `.md` file. Since these files are independent from the source components, do not regenerate these files when regenerating the components. Only update these files when the specs are updated in `context/`. Move all of these verifier files into a folder named `verifiers/`

In addition, introduce a `pipeline_verifier.py`. This file should calculate all the statistics from the parser files, and compare them to the `input.json`. If the specified values falls within 5% error margin, the verification counts as a pass. Otherwise, treat is as a fail.

### Reports

At the end of each test cases, create a `report.json` file that contains only these things:

- The source input file
- The statistics of the final parser, all attributes are taken from `converter.md`.
  
### MRD

Create an MRD verifier that can calculate the MRD and Max Depth of a given parser. MRD stands for Mean Reachability Depth and is the sum of the depth of all non-entry basic blocks, divided by the numbers of non-basic blocks. Move this verifier into `verifiers/` and use it to calculate MRD and Max Depth of the parsers during testing. The calculating pipeline is included in `extra/`