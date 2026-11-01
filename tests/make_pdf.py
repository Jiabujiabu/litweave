"""Generate the original CC0 fixture without a PDF authoring dependency."""
from pathlib import Path


def make_pdf(path):
    texts = [
        ["1 Introduction", "This original synthetic fixture tests page-addressable evidence retrieval.",
         "Dense vectors retrieve semantic paraphrases from documents.", "Hybrid retrieval combines lexical matching and semantic ranking.",
         "Reciprocal rank fusion combines ranked lists without adding raw scores."],
        ["2 Results", "The fixture includes two pages of original text for parser regression checks.",
         "These statements are synthetic test data and are not scientific findings.",
         "3 References", "Fixture Author. Original synthetic reference, not scientific evidence."]]
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Count 2 /Kids [4 0 R 6 0 R] >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, lines in enumerate(texts):
        content = b"BT /F1 11 Tf 50 750 Td 16 TL\n" + b"\n".join(("(" + line + ") Tj T*").encode("ascii") for line in lines) + b"\nET"
        content_id = 5 + i * 2
        objects.extend([f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode(),
                        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"])
    data, offsets = b"%PDF-1.4\n", [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    data += f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(path).write_bytes(data)


if __name__ == "__main__":
    make_pdf(Path(__file__).parent / "fixtures/original_cc0.pdf")
