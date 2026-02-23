// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

import com.amazon.vincent.job.VincentTestSuite
import com.amazon.vincent.job.annotation.vcf.VCFAnnotationOptions
import org.junit.Assert.{assertEquals, assertFalse}
import org.junit.runner.RunWith
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class AnnotationJobParametersTest extends AnyFunSuite with VincentTestSuite {

  test("AnnotationJobParameters defaults are set") {

    val annotationJobParameter = new AnnotationImportJobParameters(
      jobName = testJobName,
      databaseName = testDatabaseName,
      tableName = testTableName,
      tablePath = testTablePath,
      tableFormat = TableFormat.withName(testTableFormat),
      jobId = testJobId,
      inputPath = testInputPath,
      referenceArn = testReferenceArn,
      runLeftNormalization = testRunLeftNormalization.toBoolean,
      formatOptions = testFormatOptions,
      storeOptions = testStoreOptions,
      storeFormat = StoreFormat.withName(testStoreFormatName),
      annotationFields = testAnnotationFields,
      tableSortKeys = Nil)

    assertResult(testJobName)(annotationJobParameter.jobName)
    assertResult(testDatabaseName)(annotationJobParameter.databaseName)
    assertResult(testTableName)(annotationJobParameter.tableName)
    assertResult(testTablePath)(annotationJobParameter.tablePath)
    assertResult(TableFormat.ICEBERG_0)(annotationJobParameter.tableFormat)
    assertResult(testJobId)(annotationJobParameter.jobId)
    assertResult(testInputPath)(annotationJobParameter.inputPath)
    assertResult(testReferenceArn)(annotationJobParameter.referenceArn)
    assertResult(testRunLeftNormalization.toBoolean)(annotationJobParameter.runLeftNormalization)
    assertResult(testFormatOptions)(annotationJobParameter.formatOptions)
    assertResult(testStoreOptions)(annotationJobParameter.storeOptions)
    assert(StoreFormat.VCF == annotationJobParameter.storeFormat)
    assertResult(VCFAnnotationOptions(Some(false), Some(false)))(
      annotationJobParameter.vcfOptions)
    assertResult(testAnnotationFields)(annotationJobParameter.annotationFields)
  }

  test("AnnotationJobParameters GlueArgs") {
    assertResult(AnnotationImportJobParameters.glueArgs.seq)(
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
        JobParameterNames.storeFormat,
        JobParameterNames.formatOptions,
        JobParameterNames.storeOptions,
        JobParameterNames.annotationFields,
        JobParameterNames.tableSortKeys).seq)
  }

  test("Apply AnnotationJobParameters from map") {

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
      JobParameterNames.formatOptions -> testFormatOptions,
      JobParameterNames.storeOptions -> testStoreOptions,
      JobParameterNames.storeFormat -> testStoreFormatName,
      JobParameterNames.annotationFields -> testAnnotationFieldsJsonString)

    val params = AnnotationImportJobParameters(jobArgsMap)
    assertResult(testJobName)(params.jobName)
    assertResult(testDatabaseName)(params.databaseName)
    assertResult(testTableName)(params.tableName)
    assertResult(testTablePath)(params.tablePath)
    assertResult(TableFormat.ICEBERG_0)(params.tableFormat)
    assertResult(testJobId)(params.jobId)
    assertResult(testInputPath)(params.inputPath)
    assertResult(testReferenceArn)(params.referenceArn)
    assertResult(testRunLeftNormalization.toBoolean)(params.runLeftNormalization)
    assertResult(testFormatOptions)(params.formatOptions)
    assertResult(testStoreOptions)(params.storeOptions)
    assertResult(testStoreFormat)(params.storeFormat)
    assertResult(VCFAnnotationOptions(Some(false), Some(false)))(params.vcfOptions)
    assertResult(testAnnotationFields)(params.annotationFields)
  }

  test("Test empty vcf options return false") {
    val options = "{}"
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertFalse(vcfOptions.ignoreQualField.get)
    assertFalse(vcfOptions.ignoreFilterField.get)
  }

  test("test setting ignoreQualField") {
    val options = """{"vcfOptions": {"ignoreQualField": true}}"""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(Some(true), vcfOptions.ignoreQualField)
    assertEquals(vcfOptions.ignoreFilterField, None)
  }

  test("test setting ignoreFilterField") {
    val options = """{"vcfOptions": {"ignoreFilterField": true}}"""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(Some(true), vcfOptions.ignoreFilterField)
    assertEquals(vcfOptions.ignoreQualField, None)
  }

  test("setting both ignoreQualField and ignoreFilterField as true") {
    val options = """{"vcfOptions": {"ignoreFilterField": true, "ignoreQualField": true}}"""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(Some(true), vcfOptions.ignoreFilterField)
    assertEquals(Some(true), vcfOptions.ignoreQualField)
  }

  test("setting both vcfOptions as False") {
    val options = """{"vcfOptions": {"ignoreFilterField": false, "ignoreQualField": false}}"""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(Some(false), vcfOptions.ignoreFilterField)
    assertEquals(Some(false), vcfOptions.ignoreQualField)
  }

  test("vcfOptions is an empty object") {
    val options = """{"vcfOptions": {}}"""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(vcfOptions.ignoreQualField, None)
    assertEquals(vcfOptions.ignoreFilterField, None)
  }

  test("vcfOptions is an empty string") {
    val options = ""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(vcfOptions.ignoreQualField, Some(false))
    assertEquals(vcfOptions.ignoreFilterField, Some(false))
  }
}
