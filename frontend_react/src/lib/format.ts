// Number formatting matching sankeymatic's value_format setting
// value_format is two chars: first = thousands separator, second = decimal separator
// ',.': 1,234.56 (US default)
// '.,': 1.234,56 (EU)
// ' .': 1 234.56
// ' ,': 1 234,56
// 'X.': 1234.56 (no thousands)
// 'X,': 1234,56 (no thousands, comma decimal)

export function formatValue(
  value: number,
  format: string,
  prefix: string,
  suffix: string,
  fullPrecision: boolean
): string {
  const thousandsSep = format[0] === 'X' ? '' : format[0];
  const decimalSep = format[1] || '.';

  let formatted: string;

  if (fullPrecision) {
    // Show full precision but trim trailing zeros after decimal
    formatted = value.toString();
  } else {
    // Round to 2 decimal places
    formatted = value.toFixed(2);
    // Remove trailing .00
    formatted = formatted.replace(/\.?0+$/, '');
  }

  // Split into integer and decimal parts
  const parts = formatted.split('.');
  let intPart = parts[0];
  const decPart = parts[1] || '';

  // Apply thousands separator
  if (thousandsSep) {
    intPart = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, thousandsSep);
  }

  if (decPart) {
    formatted = `${intPart}${decimalSep}${decPart}`;
  } else {
    formatted = intPart;
  }

  return `${prefix}${formatted}${suffix}`;
}
