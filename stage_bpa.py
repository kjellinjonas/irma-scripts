#!/usr/bin/env python

import argparse
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


class Stager:
    def __init__(
        self,
        project,
        pipeline,
        analysis_dir,
        results_dir,
        stage_dir,
        config,
        wes=False,
        force=False,
    ):
        self.project = project
        self.pipeline = pipeline
        self.force = force
        self.config = config
        self.wes = wes
        self.analysis_dir = analysis_dir
        self.stage_dir = stage_dir
        self.results_dir = results_dir
        self.readme = Path(config["readme_dir"]) / self._get_readme()

    def run(self):
        try:
            self._check_analysis()
            if self._check_staging() and not self.force:
                logging.info(
                    f"Project {self.project} already staged. Use --force to overwrite."
                )
                return 0

            if not self._check_file_status():
                return 0

            self._prepare_for_staging()
            self._stage_files()
            self._calculate_checksums()
            delivery_readme = Path(self.stage_dir) / self.readme.name
            logging.info(f"\nProject {self.project} staged successfully!\n"
                          "Before delivery:\n"
                         f"Ensure that there are no errors in {self.config['checksums_log']}\n"
                         f"Make sure that information in {delivery_readme} is correct.\n"
                          "  Note. Remember to update checksum for README if you make any changes.\n"
                         f"Make README available to the project coordinators:\n"
                         f"  cp {delivery_readme} /proj/ngi2016001/incoming/reports/{self.project}/\n"
                     )
            return 0

        except Exception as e:
            logging.error(f"{e}")
            return 1

    def _check_analysis(self):
        if not self.results_dir.exists():
            logging.error(f"results directory not found: {self.analysis_dir}")
            raise FileNotFoundError()

    def _check_staging(self):
        return self.stage_dir.exists()

    def _check_file_status(self):
        """List files to be deleted during staging and prompt user for confirmation"""
        to_b_del = []

        if self.force and self.stage_dir.exists():
            to_b_del.append((self.stage_dir, "- Overwritten with new staging."))

        match self.pipeline:
            case "sarek":
                sarek_files = list(self.config["sarek_multiqc"].glob("*"))
                if len(sarek_files) != 0:
                    for f in sarek_files:
                        to_b_del.append(
                            (f, "- Exchanged to custom generated MultiQC files")
                        )
                else:
                    logging.info(f"No files found in {self.config['sarek_multiqc']}")
            case "rnaseq" | "methylseq":
                qualimap_dir = self.config[f"{self.pipeline}_qualimap"]
                if qualimap_dir.exists():
                    to_b_del.append(
                        (qualimap_dir, "- Compressed (.tar.gz), original removed.")
                    )

        if len(to_b_del) == 0:
            logging.info(
                "No files/directories will be modified or deleted during staging."
            )
            return True

        logging.info(
            "The following files/directories will be modified or deleted during staging:"
        )
        for item, reason in to_b_del:
            item_type = "directory" if item.is_dir() else "file"
            logging.info(f"{item} ({item_type}, {reason})")

        while True:
            response = input("Do you want to proceed with staging? (y/n): ").lower()
            if response == "y":
                return True
            elif response == "n":
                logging.info("Staging aborted.")
                return False
            else:
                logging.warning("Invalid input. Please enter 'y' or 'n'.")

    def _prepare_for_staging(self):
        match self.pipeline:
            case "sarek":
                self._prepare_sarek()
            case "rnaseq" | "methylseq":
                self._tar_qualimap()

    def _prepare_sarek(self):
        """
        Prepare sarek result dir for staging.
          - Move markduplicates from results --> analysis dir
          - Exchange sarek generated multiQC with custom report
        """
        try:
            # move markduplicate files from results to analysis dir
            if self.config["md_src"].exists():
                shutil.move(str(self.config["md_src"]), str(self.config["md_dest"]))

            if not self.config["custom_report"].exists():
                logging.info(
                    f"Custom multiQC report not found in {self.config['custom_report']}. Staging with pipeline generated report."
                )
                return

            # Replace pipeline generated multiQC with custom
            for f in self.config["sarek_multiqc"].glob("*"):
                f.unlink()

            report_replc = (
                self.config["sarek_multiqc"] / self.config["custom_report"].name
            )
            data_replc = self.config["sarek_multiqc"] / self.config["custom_data"].name
            shutil.copy(str(self.config["custom_report"]), str(report_replc))
            shutil.copy(str(self.config["custom_data"]), str(data_replc))

        except Exception as e:
            logging.error(f"Sarek preparation failed: {e}")
            raise RuntimeError()

    def _tar_qualimap(self):
        """
        Prepare rnaseq and methylseq result dir for staging
          - Compress qualimap dir
          - remove original qualimap dir
        """
        try:
            qualimap_dir = self.config[f"{self.pipeline}_qualimap"]
            if qualimap_dir.exists():
                tar_command = [
                    "tar",
                    "-czvf",
                    f"{qualimap_dir}.tar.gz",
                    str(qualimap_dir),
                ]
                subprocess.run(tar_command, check=True)
                shutil.rmtree(str(qualimap_dir))

        except Exception as e:
            logging.error(f"{self.pipeline} preparation failed: {e}")
            raise RuntimeError()

    def _stage_files(self):
        """
        Stage files for delivery.
          - Copy pipeline specific README
          - Symlink project result dir
        """
        if self.force and self.stage_dir.exists():
            shutil.rmtree(str(self.stage_dir))

        if not self.stage_dir.parent.exists():
            logging.error(
                f"Parent directory of stage directory does not exist: {self.stage_dir.parent}"
            )
            raise FileNotFoundError()

        self.stage_dir.mkdir()
        try:
            shutil.copy(str(self.readme), str(self.stage_dir))
            link_dest = self.stage_dir / self.results_dir.name
            link_dest.symlink_to(str(self.results_dir))
        except Exception as e:
            logging.error(f"Staging failed: {e}")
            raise RuntimeError()

    def _get_readme(self):
        match self.pipeline:
            case "rnaseq":
                return self.config["readme_rna"]
            case "methylseq":
                return self.config["readme_meth"]
            case "sarek":
                if self.wes:
                    return self.config["readme_wes"]
                else:
                    return self.config["readme_wgs"]

    def _calculate_checksums(self):
        """
        Submits a Slurm job to calculate checksums.

        Raises:
            RuntimeError: If any error occurs during job submission.
        """

        try:
            sbatch_command = [
                "sbatch",
                "-A",
                self.config["slurm_account"],
                "-n",
                self.config["slurm_nodes"],
                "-t",
                self.config["slurm_time"],
                "-J",
                f"checksums_{self.project}",
                "-o",
                self.config["checksums_log"],
                "--wrap",
                (
                    f"find -L {self.stage_dir} -not -type d -not -name 'checksums.md5' | "
                    f"xargs -P{self.config['slurm_nodes']} md5sum >> {self.config['checksums']}"
                ),
            ]

            result = subprocess.run(
                sbatch_command, capture_output=True, text=True, check=True
            )

            logging.info(result.stdout)

        except subprocess.CalledProcessError as e:
            logging.error(f"Slurm job submission failed: {e}")
            raise RuntimeError()
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            raise RuntimeError()


def logging_setup(analysis_dir, project):
    """Set up logging to both file and stdout"""
    log_dir = Path(analysis_dir) / "logs"
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{project}_staging_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )

def log_setup_info(project, pipeline, wes, force, analysis_dir, stage_dir, results_dir, config):
    """Logs the script setup information."""
    conf = "\n".join([f"{k}: {config[k]}" for k in config])
    logging.info(f"\n\nStaging log for {project}"
                  "\n\n### Parameters ###\n"
                 f"Project: {project}\n"
                 f"Pipeline: {pipeline}\n"
                 f"WES: {wes}\n"
                 f"Force: {force}\n"
                 f"Analysis Directory: {analysis_dir}\n"
                 f"Stage Directory: {stage_dir}\n"
                 f"Results Directory: {results_dir}\n"
                  "\n### Config ###\n"
                 f"{conf}\n\n")

def main():
    parser = argparse.ArgumentParser(
        description="Stage BPA results for delivery.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pipeline",
        required=True,
        choices=["sarek", "rnaseq", "methylseq"],
        help="Pipeline used for analysis.",
    )
    parser.add_argument(
        "--project", required=True, help="Name of project to be staged for delivery"
    )
    parser.add_argument(
        "--wes",
        action="store_true",
        help="Stage WES analysis. Requires --pipeline=sarek",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite previous staging."
    )
    parser.add_argument(
        "--analysis_path",
        default="/proj/ngi2016001/nobackup/NGI/ANALYSIS",
        help="Path to where project folder to be staged is located.",
    )
    parser.add_argument(
        "--delivery_path",
        default="/proj/ngi2016001/nobackup/NGI/DELIVERY",
        help="Path to where staging should be performed",
    )
    args = parser.parse_args()

    project = args.project
    pipeline = args.pipeline
    wes = args.wes
    force = args.force
    analysis_dir = Path(args.analysis_path) / project
    stage_dir = Path(args.delivery_path) / project
    results_dir = Path(analysis_dir) / "results"

    config = {
        "md_src": Path(results_dir) / "preprocessing" / "markduplicates",
        "md_dest": Path(analysis_dir) / "markduplicates",
        "sarek_multiqc": Path(results_dir) / "reports" / "multiqc",
        "custom_report": Path(analysis_dir)
            / "multiqc_ngi"
            / f"{project}_multiqc_report.html",
        "custom_data": Path(analysis_dir)
            / "multiqc_ngi"
            / f"{project}_multiqc_report_data.zip",
        "rnaseq_qualimap": Path(results_dir) / "star_salmon" / "qualimap",
        "methylseq_qualimap": Path(results_dir) / "qualimap",
        "checksums_log": Path(analysis_dir) / "logs" / "checksums.log",
        "checksums": Path(stage_dir) / "checksums.md5",
        "slurm_account": "ngi2016001",
        "slurm_nodes": "2",
        "slurm_time": "10:00:00",
        "readme_dir": "/proj/ngi2016001/nobackup/NGI/softlinks",
        "readme_rna": "DELIVERY.README.RNASEQ.md",
        "readme_meth": "DELIVERY.README.METHYLSEQ.md",
        "readme_wgs": "DELIVERY.README.SAREK.md",
        "readme_wes": "DELIVERY.README.SAREK.WES.md",
    }

    logging_setup(analysis_dir, project)
    log_setup_info(project, pipeline, wes, force, analysis_dir, stage_dir, results_dir, config)
    logging.info(f"Starting staging for project {project}")

    stager = Stager(
        project, pipeline, analysis_dir, results_dir, stage_dir, config, wes, force
    )
    exit_code = stager.run()
    logging.info(f"Staging finished with exit code: {exit_code}")
    exit(exit_code)


if __name__ == "__main__":
    main()
