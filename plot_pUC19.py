#!/usr/bin/env python3

import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import argparse

def get_color(row):
    if row["perCHG"] > 1.8 or row["perCHH"] > 1.8 or row["perCpG"] < 96:
        return "darkred"
    else:
        return "cadetblue"

# Set up argument parser
parser = argparse.ArgumentParser(
    description="This script plots methylation rates for pUC19 based on MultiQC data from nf-core/methylseq. Use pUC19 analysis directory as input."
)
parser.add_argument("dir", type=str, help="path to analysis directory")
parser.add_argument("--prefix", type=str, default="", help="project code or flowcell")

args = parser.parse_args()
analysis_dir = args.dir

# Define file paths
alignment_stats = os.path.join(
    analysis_dir, "results", "multiqc", "bismark", "multiqc_data", "mqc_bismark_alignment_1.txt"
)
methylation_stats = os.path.join(
    analysis_dir, "results", "multiqc", "bismark", "multiqc_data", "multiqc_bismark_methextract.txt"
)

# Check if files exist
missing_files = []
if not os.path.exists(alignment_stats):
    missing_files.append(alignment_stats)
if not os.path.exists(methylation_stats):
    missing_files.append(methylation_stats)

if missing_files:
    for file in missing_files:
        print(f"The file {file} does not exist. Please check the path.")
    exit()

# Read data
data1 = pd.read_csv(alignment_stats, delimiter="\t", usecols=["Sample", "Aligned Uniquely"])
data2 = pd.read_csv(methylation_stats, delimiter="\t", usecols=["Sample", "percent_chg_meth", "percent_chh_meth", "percent_cpg_meth"])

# Clean and merge
data1["Sample"] = data1["Sample"].str.replace("_1_val_1", "")
data2["Sample"] = data2["Sample"].str.replace("_1_val_1", "")
merged_data = pd.merge(data1, data2, on="Sample", how="left")
merged_data.columns = ["Sample", "Reads", "perCHG", "perCHH", "perCpG"]

# Plotting
plt.figure(figsize=(10, 6))
colors = merged_data.apply(get_color, axis=1)
bars = plt.bar(merged_data["Sample"], merged_data["Reads"], color=colors)

# Add horizontal line
plt.axhline(y=500, color="midnightblue", linestyle="--")

# Labels and title
plt.xlabel("Sample")
plt.ylabel("Reads")
plt.title(f"{args.prefix} pUC19")

# Rotate x-axis labels
plt.xticks(rotation=90)

# Annotate bars
for bar, row in zip(bars, merged_data.itertuples()):
    if row.perCHG > 1.8 or row.perCHH > 1.8 or row.perCpG < 96:
        labels = []
        if row.perCHG > 1.8:
            labels.append(f"{row.perCHG:.1f} %mCHG")
        if row.perCHH > 1.8:
            labels.append(f"{row.perCHH:.1f} %mCHH")
        if row.perCpG < 96:
            labels.append(f"{row.perCpG:.1f} %mCpG")
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            "\n".join(labels),
            ha="center",
            va="bottom",
        )

# Legend
legend_elements = [
    Line2D([0], [0], color="darkred", lw=4, label="Failed"),
    Line2D([0], [0], color="cadetblue", lw=4, label="OK"),
]
plt.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(1.02, 0.5), title="QC")

# Save plot
plt.tight_layout(rect=[0, 0, 1, 1])
output_path = os.path.join(analysis_dir, f"{args.prefix}_pUC19.png")
plt.savefig(output_path)

print(f"The plot has been saved to '{output_path}'")
