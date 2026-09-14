"""
KML/KMZ Contour Parser — extracts contour lines + elevation values from a KML file.

Handles both:
  - .kml (plain XML)
  - .kmz (a zipped .kml — unzipped transparently before parsing)

KML structure this is built against (confirmed against the real sample file,
not guessed): each contour line is a <Placemark>, whose <name> holds the
elevation value (e.g. "277.0"), and whose <LineString><coordinates> holds the
line itself as "lon,lat lon,lat ..." pairs (no altitude in the coordinate
tuples — elevation lives only in <name>).

This is written generically off the KML structure (Placemark -> name ->
LineString -> coordinates), not off any value specific to the sample file,
so it should generalize to other contour maps with the same export format
(this looks like standard output from a "KML contour generator" tool, which
is a common enough format that other sample maps are likely to match it).
"""

import zipfile
import io
from lxml import etree

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


class ContourParseError(Exception):
    """Raised when a KML/KMZ file can't be parsed or contains no usable contour lines."""
    pass


def load_kml_bytes(file_bytes: bytes, filename: str) -> bytes:
    """
    Returns raw KML XML bytes, unzipping first if the file is a KMZ.
    in  -> raw file bytes, original filename (used only to detect .kmz vs .kml)
    out -> KML XML bytes
    """
    if filename.lower().endswith(".kmz"):
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                # KMZ files conventionally contain one top-level .kml file,
                # usually named doc.kml, but we don't assume the name —
                # just take the first .kml entry found.
                kml_names = [n for n in z.namelist() if n.lower().endswith(".kml")]
                if not kml_names:
                    raise ContourParseError("KMZ file contains no .kml entry.")
                return z.read(kml_names[0])
        except zipfile.BadZipFile:
            raise ContourParseError("File has a .kmz extension but isn't a valid zip archive.")
    return file_bytes


def parse_contours(file_bytes: bytes, filename: str) -> list[dict]:
    """
    Parses a KML/KMZ file into a list of contour lines.

    in  -> raw file bytes, original filename
    out -> list of {"elevation": float, "coordinates": [(lon, lat), ...]}

    Raises: ContourParseError if the file can't be parsed or has no contour lines.
    """
    kml_bytes = load_kml_bytes(file_bytes, filename)

    try:
        root = etree.fromstring(kml_bytes)
    except etree.XMLSyntaxError as e:
        raise ContourParseError(f"Invalid KML/XML: {e}")

    placemarks = root.findall(".//kml:Placemark", KML_NS)
    if not placemarks:
        raise ContourParseError("No <Placemark> elements found — not a recognized contour KML.")

    contours = []
    for pm in placemarks:
        name_el = pm.find("kml:name", KML_NS)
        coords_el = pm.find(".//kml:LineString/kml:coordinates", KML_NS)

        if name_el is None or coords_el is None or not coords_el.text:
            continue  # skip malformed placemarks rather than failing the whole file

        try:
            elevation = float(name_el.text.strip())
        except (ValueError, AttributeError):
            continue  # name isn't a numeric elevation — not a contour line we can use

        coord_pairs = []
        for token in coords_el.text.strip().split():
            parts = token.split(",")
            if len(parts) < 2:
                continue
            lon, lat = float(parts[0]), float(parts[1])
            coord_pairs.append((lon, lat))

        if len(coord_pairs) >= 2:
            contours.append({"elevation": elevation, "coordinates": coord_pairs})

    if not contours:
        raise ContourParseError("Parsed the file but found no usable contour lines with elevation + coordinates.")

    return contours
