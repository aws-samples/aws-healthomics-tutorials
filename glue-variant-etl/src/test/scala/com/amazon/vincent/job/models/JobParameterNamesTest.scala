// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

import org.junit.runner.RunWith
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class JobParameterNamesTest extends AnyFunSuite {

  test("JobParametersNames are correct") {
    assertResult("JOB_NAME")(JobParameterNames.jobName)
    assertResult("GLUE_DATABASE_NAME")(JobParameterNames.databaseName)
    assertResult("GLUE_TABLE_NAME")(JobParameterNames.tableName)
    assertResult("GLUE_TABLE_PATH")(JobParameterNames.tablePath)
    assertResult("TABLE_FORMAT")(JobParameterNames.tableFormat)
    assertResult("IMPORT_JOB_ID")(JobParameterNames.jobId)
    assertResult("INPUT_PATH")(JobParameterNames.inputPath)
    assertResult("REFERENCE_ARN")(JobParameterNames.referenceArn)
    assertResult("RUN_LEFT_NORMALIZATION")(JobParameterNames.runLeftNormalization)
    assertResult("STORE_FORMAT")(JobParameterNames.storeFormat)
    assertResult("FORMAT_OPTIONS")(JobParameterNames.formatOptions)
    assertResult("STORE_OPTIONS")(JobParameterNames.storeOptions)
    assertResult("ANNOTATION_FIELDS")(JobParameterNames.annotationFields)
  }

}
