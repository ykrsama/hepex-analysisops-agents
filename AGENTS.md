# AGENTS.md - Your Workspace

This folder is home. Treat it that way.

## First Run

Enter the analysis root directory `/root/analysis/`, install environment (Spawn subagent to run skill `ana-setup-env`) and then source environment.

According to user's intention, select the workflow in `Analysis Workflow References` to start.
- Follow user's configuration e.g. sample, cuts, fitting model, etc if provided.
- If no exactly matched analysis, select the most relevant reference and make your own workflow)

Note: There are already downloaded root files in `/home/agent/analysis/cache` .

Don't ask permission. Just do it.

## Requirements

- **Code Centralization:** Save all analysis **scripts** and **outputs** in the `/root/analysis/`, NOT in any other directory
- **Log to file**: When running scripts/commands, use `tee` to save the log to local file.
**Code Style**
- **Modular**: Save code of each sub-task to separate files/modules, NOT a single file for the whole workflow.
- **Config-Driven**: Use YAML files to define cuts and other parameters.
- **Iterative & Visual**: Output plots at each major step for validation.

## Analysis Workflow References

### Higgs to $\gamma\gamma$

<workflow **Higgs to $\gamma\gamma$ analysis**>
  <description>
    ATLAS Open Data Analysis Pipeline for Rediscovering the Higgs Boson via the H -> yy channel.
  </description>
  <sub-task 1. **Install Environment**: Spawn a subagent and load skill `ana-setup-env`>
    - Goal: Install Environment
    - Repository/root: `/root/analysis`
    - Actions allowd: read files, edit files, run all commands
    - Deliverable: Short summary of environment installation
  </sub-task>
  <sub-task 2. **Source Environment**: `source .venv/bin/activate` />
  <sub-task 3. **Access Online Data Access & Select Variables**: Spawn a subagent and load skill `ana-create-data-loader`>
    - Goal: Create data loader module file
    - Repository/root: `/root/analysis`
    - Actions allowd: read files, edit files, run all commands
    - Input: the following complete metadata 
    <metadata>
      {
        "release": "2025e-13tev-beta",
        "skim": "GamGam",
        "defs": {
            'Data': {'dids': ['data']}
        },
        "tree_name": "analysis",
        "variables": ["photon_pt", "photon_eta", "photon_phi", "photon_e", "photon_isTightID", "photon_ptcone20"]
      }
    </metadata>
    - Deliverable: Short summary of data loader module creation
  </sub-task>
  <sub-task 4. **Define Signal Region (Event Selection, Cuts, Variable Calculation)** >
    <step 1. Read complete content of file `/root/.openharness/skills/ana-create-event-selector/references/hyy_selections.json` />
    <step 2. **You** load and execute skill `ana-create-event-selector` />
  </sub-task>
  <sub-task 5. **Statistical Fitting**>
    <step 1. Read complete content of file `/root/.openharness/skills/ana-fitting/references/hyy_fitting.json` />
    <step 2. **You** load and execute skill `ana-fitting` />
  </sub-task>
</workflow>

### Find the Z boson

<workflow **Z to $\mu\mu$ analysis**>
  <description>
    ATLAS Open Data Analysis Pipeline for finding the Z Boson via the di-muon channel.
  </description>
  <sub-task 1. **Install Environment**: Spawn a subagent and load skill `ana-setup-env`>
    - Goal: Install Environment
    - Repository/root: `/root/analysis`
    - Actions allowd: read files, edit files, run all commands
    - Deliverable: Short summary of environment installation
  </sub-task>
  <sub-task 2. **Source Environment**: `source .venv/bin/activate` />
  <sub-task 3. **Access Online Data Access & Select Variables**: Spawn a subagent and load skill `ana-create-data-loader`>
    - Goal: Create data loader module file
    - Repository/root: `/root/analysis`
    - Actions allowd: read files, edit files, run all commands
    - Input: the following complete metadata 
    <metadata>
      {
        "release": "2025e-13tev-beta",
        "skim": "2muons",
        "defs": {
            "Data": {"dids": ["data"]}
        },
        "tree_name": "analysis",
        "variables": ["lep_pt", "lep_eta", "lep_phi", "lep_e"]
      }
    </metadata>
    - Deliverable: Short summary of data loader module creation
  </sub-task>
  <sub-task 4. **Define Signal Region (Event Selection, Cuts, Variable Calculation)** >
    <step 1. Read complete content of file `/root/.openharness/skills/ana-create-event-selector/references/z_mumu_selections.json` />
    <step 2. **You** load and execute skill `ana-create-event-selector` />
  </sub-task>
  <sub-task 5. **Statistical Fitting**>
    <step 1. Read complete content of file `/root/.openharness/skills/ana-fitting/references/z_mumu_fitting.json` />
    <step 2. **You** load and execute skill `ana-fitting` />
  </sub-task>
</workflow>

### Higgs to $\mu\mu$

<workflow **Higgs to $\mu\mu$ analysis**>
  <description>
    ATLAS Open Data Analysis Pipeline for searching for the rare decay of a Higgs Boson via the H -> \mu^+\mu^- channel.
  </description>
  <sub-task 1. **Install Environment**: Spawn a subagent and load skill `ana-setup-env`>
    - Goal: Install Environment
    - Repository/root: `/root/analysis`
    - Actions allowd: read files, edit files, run all commands
    - Deliverable: Short summary of environment installation
  </sub-task>
  <sub-task 2. **Source Environment**: `source .venv/bin/activate` />
  <sub-task 3. **Access Online Data Access & Select Variables**: Spawn a subagent and load skill `ana-create-data-loader`>
    - Goal: Create data loader module file
    - Repository/root: `/root/analysis`
    - Actions allowd: read files, edit files, run all commands
    - Input: the following complete metadata
    <metadata>
      {
        "release": "2025e-13tev-beta",
        "skim": "2muons",
        "defs": {
            "Data": {"dids": ["data"]},
            "Signal Higgs": {"dids": [345106, 345098, 345097], "color": "purple"},
            "Background mu_mu": {"dids": [700323, 700324, 700325], "color": "orange"},
            "Background ttbar": {"dids": [410470], "color": "cyan"}
        },
        "tree_name": "analysis",
        "variables": ["trigM", "lep_isTrigMatched", "lep_n", "met", "lep_type", "lep_pt", "lep_charge", "lep_isMediumID", "lep_isLooseIso", "jet_e", "jet_pt", "jet_btag_quantile", "jet_eta", "jet_phi", "lep_eta", "lep_phi", "lep_e"],
        "weight_variables": ["ScaleFactor_MUON", "ScaleFactor_MuTRIGGER", "ScaleFactor_PILEUP", "ScaleFactor_FTAG", "mcWeight", "sum_of_weights", "xsec", "filteff", "kfac"]
      }
    </metadata>
    - Deliverable: Short summary of data loader module creation
  </sub-task>
  <sub-task 4. **Define Signal Region (Event Selection, Cuts, Variable Calculation)** >
    <step 1. Read complete content of file `/root/.openharness/skills/ana-create-event-selector/references/hmumu_selections.json` />
    <step 2. **You** load and execute skill `ana-create-event-selector` />
  </sub-task>
  <sub-task 5. **Statistical Plotting & Fitting**>
    <step 1. Read complete content of file `/root/.openharness/skills/ana-fitting/references/hmumu_fitting.json` />
    <step 2. **You** load and execute skill `ana-fitting` />
  </sub-task>
</workflow>

### Higgs to bb

<workflow **Higgs to bb analysis**>
  <description>
    ATLAS Open Data Analysis Pipeline for searching for the Higgs Boson via the H -> bb channel (0-lepton channel).
  </description>
  <sub-task 1. **Install Environment**: Spawn subagent to run skill `ana-setup-env`>
    - Goal: Install Environment
    - Repository/root: `/root/analysis`
    - Actions allowd: read files, edit files, run all commands
    - Deliverable: Short summary of environment installation
  </sub-task>
  <sub-task 2. **Source Environment**: `source .venv/bin/activate` />
  <sub-task 3. **Access Online Data Access & Select Variables**: Spawn subagent to run skill `ana-create-data-loader`, pass the following complete metadata to the subagent prompt>
    - Goal: Create data loader module file
    - Repository/root: `/root/analysis`
    - Actions allowd: read files, edit files, run all commands
    - Input: the following complete metadata 
    <metadata>
      {
        "release": "2025e-13tev-beta",
        "skim": "2bjets",
        "defs": {
            "Data": {"dids": ["data"]},
            "Signal": {"dids": [345056, 345058, 345949, 346311, 346312], "color": "red"},
            "Background ttbar": {"dids": [410470, 410471], "color": "yellow"},
            "Background Single top": {"dids": [410644, 410645, 410658, 410659, 601624, 601628], "color": "orange"},
            "Background V+jets": {"dids": [700320, 700321, 700322, 700323, 700324, 700325, 700335, 700336, 700337, 700338, 700339, 700340, 700341, 700342, 700343, 700344, 700345, 700346, 700347, 700348, 700349, 700467, 700468, 700469, 700470, 700471, 700472, 700792, 700793, 700794], "color": "blue"},
            "Background Diboson": {"dids": [700488, 700489, 700490, 700491, 700492, 700493, 700494, 700495, 700496, 700195, 700196, 700199, 700200, 700201], "color": "grey"}
        },
        "tree_name": "analysis",
        "variables": ["jet_jvt", "jet_n", "jet_pt", "jet_eta", "jet_phi", "jet_e", "met", "met_phi", "trigMET", "jet_btag_quantile", "lep_isLooseIso", "lep_d0sig", "lep_z0", "lep_type", "lep_eta", "lep_e", "lep_pt", "lep_isTightID", "lep_isLooseID"],
        "weight_variables": ["xsec", "mcWeight", "ScaleFactor_PILEUP", "ScaleFactor_FTAG", "ScaleFactor_JVT", "filteff", "kfac", "sum_of_weights"]
      }
      </metadata>
    - Deliverable: Short summary of data loader module creation
  </sub-task>
  <sub-task 4. **Define Signal Region (Event Selection & Cuts, Variable Calculation)**>
    <step 1. Read complete content of file `/root/.openharness/skills/ana-create-event-selector/references/hbb_selections.json` />
    <step 2. **You** directly run skill `ana-create-event-selector` />
  </sub-task>
  <sub-task 5. **Statistical Fitting**>
    <step 1. Read complete content of file `/root/.openharness/skills/ana-fitting/references/hbb_fitting.json` />
    <step 2. **You** directly run skill `ana-fitting` />
  </sub-task>
</workflow>

## Make It Yours

This is a starting point. Add your own conventions, style, and rules as you figure out what works.

### Troubleshooting Checklist

1.  **Cutflow Mismatch**: 
    - Check **Lepton Isolation**: Did you veto based on `lep_isLooseIso` and `lep_z0 < 0.5`?
    - Check **B-tagging**: Is the quantile threshold correct for the targeted efficiency?
2.  **Mass Peak Offset**:
    - **PtReco Balance**: Applying PtReco to both jets in a $H \to bb$ search can shift the peak to $\sim 140$ GeV. Re-calibrate to leading jet or use standard reference constants.
    - **Pure Signal Mean vs S+B Fit**: Never trust the weighted mean of the signal MC alone (tails pull it high). Always use a **Signal + Background** fit on data.
3.  **Fit Failure**:
    - **Background Model**: Simple polynomials may fail at low-mass thresholds. Use **Bernstein Polynomials** or **Exponential-Polynomial** combinations for complex thresholds.
