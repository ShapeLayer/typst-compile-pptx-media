using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Validation;
if (args.Length == 0) {
  Console.Error.WriteLine("Usage: OpenXmlValidator file.pptx [file.pptx ...]");
  return 2;
}
foreach (var path in args) {
  using var doc = PresentationDocument.Open(path, false);
  var errors = new OpenXmlValidator(FileFormatVersions.Office2019).Validate(doc).ToList();
  Console.WriteLine($"{path}: {errors.Count} errors");
  foreach (var error in errors) Console.WriteLine($"{error.Part?.Uri}: {error.Path?.XPath}: {error.Description}");
  if (errors.Count > 0) Environment.ExitCode = 1;
}

return Environment.ExitCode;
