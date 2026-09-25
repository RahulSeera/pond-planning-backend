"""
KML/KMZ Contour Parser — extracts contour lines + elevation values from a KML file.

Handles:
  - .kml (plain XML)
  - .kmz (zipped .kml archives)
  - Numeric elevation in <name> (e.g. "277.0")
  - Alphanumeric elevation labels (e.g. "Contour 280m", "Elev: 275.5")
  - Fallback to 3D coordinate Z-values (<coordinates>lon,lat,alt ...</coordinates>)
  - Robust error handling for empty files, invalid archives, and malformed tags
"""

import zipfile
import io
import re
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
    if not file_bytes or len(file_bytes.strip()) == 0:
        raise ContourParseError("Uploaded file is empty (0 bytes).")

    if filename.lower().endswith(".kmz"):
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                kml_names = [n for n in z.namelist() if n.lower().endswith(".kml")]
                if not kml_names:
                    raise ContourParseError("KMZ file contains no .kml entry.")
                return z.read(kml_names[0])
        except zipfile.BadZipFile:
            raise ContourParseError("File has a .kmz extension but is not a valid zip archive.")
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

    # Search for placemarks with or without namespace prefix
    placemarks = root.findall(".//kml:Placemark", KML_NS)
    if not placemarks:
        placemarks = root.findall(".//Placemark")

    if not placemarks:
        raise ContourParseError("No <Placemark> elements found — not a recognized contour KML.")

    contours = []
    for pm in placemarks:
        name_el = pm.find("kml:name", KML_NS)
        if name_el is None:
            name_el = pm.find("name")

        coords_el = pm.find(".//kml:LineString/kml:coordinates", KML_NS)
        if coords_el is None:
            coords_el = pm.find(".//LineString/coordinates")

        if coords_el is None or not coords_el.text:
            continue

        elevation = None
        if name_el is not None and name_el.text:
            raw_text = name_el.text.strip()
            try:
                elevation = float(raw_text)
            except ValueError:
                m = re.search(r"[-+]?\d*\.?\d+", raw_text)
                if m:
                    try:
                        elevation = float(m.group(0))
                    except ValueError:
                        pass

        coord_pairs = []
        z_values = []
        for token in coords_el.text.strip().split():
            parts = token.split(",")
            if len(parts) >= 2:
                try:
                    lon, lat = float(parts[0]), float(parts[1])
                    coord_pairs.append((lon, lat))
                    if len(parts) >= 3 and parts[2].strip():
                        z_values.append(float(parts[2]))
                except ValueError:
                    continue

        if elevation is None and z_values:
            elevation = float(sum(z_values) / len(z_values))

        if elevation is not None and len(coord_pairs) >= 2:
            contours.append({"elevation": elevation, "coordinates": coord_pairs})

    if not contours:
        raise ContourParseError("Parsed the file but found no usable contour lines with elevation and coordinates.")

    return contours
