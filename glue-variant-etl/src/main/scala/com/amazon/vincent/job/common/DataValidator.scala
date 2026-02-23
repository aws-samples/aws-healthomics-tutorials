// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

import com.amazon.vincent.job.common.DataValidationStatuses.{FAIL_PARTIAL_WRITE, PASS}
import com.amazon.vincent.job.models.exceptions.{DataValidationException, VincentUserException}
import com.amazonaws.services.glue.GlueContext
import com.amazonaws.services.glue.log.GlueLogger
import org.apache.spark.sql.DataFrame

object DataValidator {
  def check(
      df: DataFrame,
      glueContext: GlueContext,
      tableLocation: String,
      importJobId: String): DataValidationStatuses.Value = {
    val logger = new GlueLogger

    val expectedRowCount = df.count()
    logger.info("The expected row count: " + expectedRowCount)

    val rowCountQueryString =
      s"SELECT COUNT (*) FROM $tableLocation WHERE importjobid = '$importJobId'"

    logger.info("SQL query ran: " + rowCountQueryString)

    val actualRowCount = glueContext.getSparkSession
      .sql(rowCountQueryString)
      .collectAsList()
      .get(0)
      .getLong(0)

    logger.info("The actual row count: " + actualRowCount)

    val diff = expectedRowCount - actualRowCount
    logger.info(
      s"ExpectedRowCount ($expectedRowCount) - ActualRowCount ($actualRowCount) = Diff ($diff)")

    if (actualRowCount == 0 && expectedRowCount == 0) {
      throw new VincentUserException("Cannot import file with 0 rows.")
    } else if (actualRowCount == 0 && expectedRowCount > 0) {
      throw new DataValidationException(
        s"Data quality checks failed. ExpectedRows=$expectedRowCount, ActualRows=$actualRowCount (Expected-Actual)=$diff for import jobId: $importJobId")
    } else if (diff == 0) {
      logger.info(s"Data quality checks passed.")
      PASS
    } else {
      logger.error(
        s"Data quality checks failed. Partial write to the table is observed. Expected row count: $expectedRowCount, only got: $actualRowCount for import jobId: $importJobId")
      logger.info(
        s"Letting this job to succeeded. Logging this to Cloudwatch for further investigation and triage")
      // Log partial write behavior in Cloudwatch
      FAIL_PARTIAL_WRITE
    }
  }
}
