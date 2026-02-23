// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

import com.amazon.vincent.job.VincentTestSuite
import org.junit.runner.RunWith
import org.scalatest.BeforeAndAfterEach
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class VariantImportJobParametersTest
    extends AnyFunSuite
    with BeforeAndAfterEach
    with VincentTestSuite {

  var params: VariantImportJobParameters = _

  override def beforeEach(): Unit = {
    params = new VariantImportJobParameters(
      jobName = testJobName,
      databaseName = testDatabaseName,
      tableName = testTableName,
      tablePath = testTablePath,
      tableFormat = TableFormat.withName(testTableFormat),
      jobId = testJobId,
      inputPath = testInputPath,
      referenceArn = testReferenceArn,
      runLeftNormalization = testRunLeftNormalization.toBoolean,
      annotationFields = testAnnotationFields,
      tableSortKeys = Nil)
    super.beforeEach()
  }

  test("VariantImportJobParameters defaults are set correctly") {
    assertResult(testJobName)(params.jobName)
    assertResult(testDatabaseName)(params.databaseName)
    assertResult(testTableName)(params.tableName)
    assertResult(testTablePath)(params.tablePath)
    assertResult(TableFormat.ICEBERG_0)(params.tableFormat)
    assertResult(testJobId)(params.jobId)
    assertResult(testInputPath)(params.inputPath)
    assertResult(testReferenceArn)(params.referenceArn)
    assertResult(testRunLeftNormalization.toBoolean)(params.runLeftNormalization)
    assertResult(testAnnotationFields)(params.annotationFields)
    assertResult(testTableSortKeys)(params.tableSortKeys)
  }

  test("Check if params provided can be used for parsing vep") {
    assertResult(false)(params.supportsVEPParsing)
    assertResult(true)(params.copy(tableFormat = TableFormat.ICEBERG_1).supportsVEPParsing)
    assertResult(false)(
      params.copy(annotationFields = new AnnotationFields(None)).supportsVEPParsing)
  }

  test("VariantImportJobParameters GlueArgs") {

    assertResult(VariantImportJobParameters.glueArgs.seq)(
      Array(
        JobParameterNames.jobName,
        JobParameterNames.databaseName,
        JobParameterNames.tableName,
        JobParameterNames.tablePath,
        JobParameterNames.tableFormat,
        JobParameterNames.jobId,
        JobParameterNames.inputPath,
        JobParameterNames.referenceArn,
        JobParameterNames.runLeftNormalization,
        JobParameterNames.annotationFields,
        JobParameterNames.tableSortKeys).seq)
  }

  test("Apply VariantImportJobParameters from map") {

    val jobArgsMap = Map(
      JobParameterNames.jobName -> testJobName,
      JobParameterNames.databaseName -> testDatabaseName,
      JobParameterNames.tableName -> testTableName,
      JobParameterNames.tablePath -> testTablePath,
      JobParameterNames.tableFormat -> testTableFormat,
      JobParameterNames.jobId -> testJobId,
      JobParameterNames.inputPath -> testInputPath,
      JobParameterNames.referenceArn -> testReferenceArn,
      JobParameterNames.runLeftNormalization -> testRunLeftNormalization,
      JobParameterNames.annotationFields -> testAnnotationFieldsJsonString)

    val params = VariantImportJobParameters(jobArgsMap)
    assertResult(testJobName)(params.jobName)
    assertResult(testDatabaseName)(params.databaseName)
    assertResult(testTableName)(params.tableName)
    assertResult(testTablePath)(params.tablePath)
    assertResult(TableFormat.ICEBERG_0)(params.tableFormat)
    assertResult(testJobId)(params.jobId)
    assertResult(testInputPath)(params.inputPath)
    assertResult(testReferenceArn)(params.referenceArn)
    assertResult(testRunLeftNormalization.toBoolean)(params.runLeftNormalization)
    assertResult(testAnnotationFields)(params.annotationFields)
  }

}
