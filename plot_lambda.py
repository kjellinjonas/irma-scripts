#!/usr/bin/env python3

import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import argparse

def get_color(value):
    if value <= 0.7:
        return "cadetblue"
    elif value <= 1:
        return "darkorange"
    else:
        return "darkred"

# Set up argument parser
parser = argparse.ArgumentParser(
        description="This script plots methylation rate in CpG sites for lambda based on MultiQC data from nf-core/methylseq. Use path to lambda control analysis directory as input."
)
parser.add_argument("dir", type=str, help="path to analysis directory")
parser.add_argument("--prefix", type=str, default="", help="project code or flowcell")

args = parser.parse_args()

# Find the paths to the two files from the provided working directory
analysis_dir = args.dir
alignment_stats = os.path.join(
    analysis_dir,
    "results",
    "multiqc",
    "bismark",
    "multiqc_data",
    "mqc_bismark_alignment_1.txt",
)
methylation_stats = os.path.join(
    analysis_dir,
    "results",
    "multiqc",
    "bismark",
    "multiqc_data",
    "multiqc_bismark_methextract.txt",
)

# Check if the files exist
missing_files = []

if not os.path.exists(alignment_stats):
    missing_files.append(alignment_stats)

if not os.path.exists(methylation_stats):
    missing_files.append(methylation_stats)

if missing_files:
    for file in missing_files:
        print(f"The file {file} does not exist. Please check the path.")
    exit()

data1 = pd.read_csv(
    alignment_stats, delimiter="\t", usecols=["Sample", "Aligned Uniquely"]
)
data2 = pd.read_csv(
    methylation_stats, delimiter="\t", usecols=["Sample", "percent_cpg_meth"]
)
merged_data = pd.merge(data1, data2, on="Sample", how="left")
merged_data["Sample"] = merged_data["Sample"].str.replace("_1_val_1", "")
merged_data.columns = ["Sample", "Reads", "%mCpG"]

# Plotting
plt.figure(figsize=(10, 6))

colors = merged_data["%mCpG"].apply(get_color)

# Create bar plot
bars = plt.bar(merged_data["Sample"], merged_data["Reads"], color=colors)

# Add horizontal line at y=5000
plt.axhline(y=5000, color="midnightblue", linestyle="--")

# Add labels and title
plt.xlabel("Sample")
plt.ylabel("Reads")
plt.title(f'{args.prefix} Lambda')

# Rotate x-axis labels for better readability
plt.xticks(rotation=90)

# Add %mCpG values on top of the bars if they are over 0.7
for bar, value in zip(bars, merged_data["%mCpG"]):
    if value > 0.7:
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{value:.1f} %mCpG",
            ha="center",
            va="bottom",
        )

# Add legend
legend_elements = [
    Line2D([0], [0], color="cadetblue", lw=4, label="OK"),
    Line2D([0], [0], color="darkorange", lw=4, label="<1.0"),
    Line2D([0], [0], color="darkred", lw=4, label="Failed"),
]

plt.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(1.02, 0.5), title="%mCpG QC")

# Save plot to a file in the provided working directory
plt.tight_layout(rect=[0,0,1,1])
plt.savefig(os.path.join(analysis_dir, f'{args.prefix}_lambda.png'))

print(f"The plot has been saved to '{os.path.join(analysis_dir, f'{args.prefix}_lambda.png')}'")
