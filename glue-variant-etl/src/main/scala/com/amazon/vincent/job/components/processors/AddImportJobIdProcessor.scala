// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components.processors

import com.amazon.vincent.job.models.ImportJobParameters
import org.apache.spark.sql.DataFrame
import org.apache.spark.sql.functions.lit

// Add JobId to the schema which will be used for a delete API by jobId and sampleId.
class AddImportJobIdProcessor() extends VincentJobProcessor[ImportJobParameters] {
  override def process(df: DataFrame, vincentJobParameters: ImportJobParameters): DataFrame = {
    df.withColumn("importjobid", lit(vincentJobParameters.jobId))
  }
}
