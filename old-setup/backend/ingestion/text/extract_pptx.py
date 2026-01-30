import os
import logging
import subprocess

logger = logging.getLogger(__name__)


def convert_ppt_to_pdf(pptx_path: str, output_path: str) -> str:
    """
    Convert PowerPoint (.ppt or .pptx) to PDF using LibreOffice.

    Args:
        pptx_path: Path to the PowerPoint file
        output_path: Path where the PDF should be saved

    Returns:
        Path to the generated PDF file

    Raises:
        RuntimeError: If LibreOffice is not found or conversion fails
    """
    # Get LibreOffice path from environment or use defaults
    libreoffice_path = os.environ.get(
        "LIBREOFFICE_PATH",
        "libreoffice"  # Default command
    )

    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    try:
        # LibreOffice command for headless PDF conversion
        # --headless: Run without GUI
        # --convert-to pdf: Convert to PDF format
        # --outdir: Output directory
        cmd = [
            libreoffice_path,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", output_dir,
            pptx_path
        ]

        logger.info(f"Converting {pptx_path} to PDF using LibreOffice")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")

        # LibreOffice outputs with the same name but .pdf extension
        base_name = os.path.splitext(os.path.basename(pptx_path))[0]
        generated_pdf = os.path.join(output_dir, f"{base_name}.pdf")

        if not os.path.exists(generated_pdf):
            raise RuntimeError(f"PDF not generated at expected path: {generated_pdf}")

        # Rename if output_path is different
        if generated_pdf != output_path:
            os.rename(generated_pdf, output_path)

        logger.info(f"Successfully converted to PDF: {output_path}")
        return output_path

    except FileNotFoundError:
        raise RuntimeError(
            f"LibreOffice not found at '{libreoffice_path}'. "
            "Please install LibreOffice and set LIBREOFFICE_PATH environment variable."
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("LibreOffice conversion timed out after 5 minutes")
    except Exception as e:
        logger.error(f"Failed to convert PowerPoint to PDF: {e}", exc_info=True)
        raise
