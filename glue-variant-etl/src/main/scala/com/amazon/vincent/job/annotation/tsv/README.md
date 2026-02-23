# TSV Annotation Parser

The TSV annotation parser for reading annotaiton in tsv format and does the following

1) Load as spark dataframe
2) For structured annotations, convert to zero base half-open coordinates
3) If REF/ALT information are available (`CHR_POS_REF_ALT` and `CHR_START_END_REF_ALT` format),
   1) Runs left normalization
   2) Otherwise, checks that start positions of an annotation is within the length of the contig defined in the reference

## Options

Please refer to smithy models at https://code.amazon.com/packages/AwsVincentDataPlaneModel/blobs/6fef9a6cb994bcf5b8f1d2491ea524fbac4ea1b6/--/model/operations/import/annotation/startAnnotationImportJob.smithy#L67
for the different options that can be used for the annotation parser

## Running Import Annotation Parser Job

Until we set up a dev stack that will create glue job  on AwsVincentJobCDK, the way to test is to deploy the
jar via AwsVincentJobsCDK and invoke it via the import annotation api, or to rerun an existing glue job.

