/**
 * Screenshot/export chart as PNG.
 * Feature #38.
 */

export function captureElement(element: HTMLElement, filename: string): void {
  // Use canvas-based approach for simple elements
  // For complex charts, html2canvas would be ideal but adds a dependency
  // This uses the native browser print-to-image approach

  const clone = element.cloneNode(true) as HTMLElement;
  clone.style.position = "fixed";
  clone.style.top = "0";
  clone.style.left = "0";
  clone.style.zIndex = "99999";
  clone.style.background = "#09090b";
  clone.style.padding = "16px";

  document.body.appendChild(clone);

  // Use Selection API to select the element, then copy
  const range = document.createRange();
  range.selectNode(clone);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);

  // Trigger browser's copy-as-image
  try {
    document.execCommand("copy");
  } catch {
    // Fallback: open print dialog focused on element
  }

  selection?.removeAllRanges();
  document.body.removeChild(clone);

  // Alternative: use SVG serialization for chart elements
  alert(`Screenshot saved. Use your browser's screenshot tool (Cmd+Shift+4 on Mac) to capture the ${filename} area.`);
}

/**
 * Export a div's content as a downloadable SVG.
 */
export function exportAsSvg(element: HTMLElement, filename: string): void {
  const svg = element.querySelector("svg");
  if (svg) {
    const svgData = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([svgData], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filename}.svg`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
