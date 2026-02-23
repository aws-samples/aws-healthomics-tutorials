// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation

import com.amazon.vincent.job.common.ReferenceStoreDao
import com.amazon.vincent.job.components.processors.{
  AddImportJobIdProcessor,
  DropVCFOptionalFieldsProcessor,
  ExplodeGenotypeProcessor,
  MissingAndAdditionalFieldsProcessor,
  VCFLeftNormalizationProcessor,
  VEPAnnotationProcessor
}
import com.amazon.vincent.job.components.{
  AnnotationVCFJobComponent,
  DataFrameV2Writer,
  VCFDataFrameLoader
}
import com.amazon.vincent.job.models.{AnnotationImportJobParameters, StoreFormat, TableFormat}
import com.amazon.vincent.job.{AnnotationVCFJob, VincentTestSuite}
import org.apache.spark.sql.QueryTest
import org.apache.spark.sql.functions.col
import org.apache.spark.sql.test.SharedSparkSession
import org.junit.runner.RunWith
import org.mockito.MockitoSugar.mock
import org.scalatest.BeforeAndAfterEach
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class VCFAnnotationImportJobTest
    extends QueryTest
    with VincentTestSuite
    with SharedSparkSession
    with BeforeAndAfterEach {

  var annotationJobParameter: AnnotationImportJobParameters = _
  var mockReferenceStoreDao: ReferenceStoreDao = _
  var mockWriter: DataFrameV2Writer = _

  def createTestComponent(
      parameters: AnnotationImportJobParameters): AnnotationVCFJobComponent = {
    AnnotationVCFJobComponent(
      spark,
      mockWriter,
      new VCFDataFrameLoader(),
      Seq(
        new VCFLeftNormalizationProcessor(mockReferenceStoreDao, testVincentLogger),
        VEPAnnotationProcessor(spark, parameters, testVincentLogger),
        new ExplodeGenotypeProcessor,
        new AddImportJobIdProcessor,
        new DropVCFOptionalFieldsProcessor,
        new MissingAndAdditionalFieldsProcessor(testVincentLogger)),
      testVincentLogger)
  }

  override def beforeEach(): Unit = {
    mockReferenceStoreDao = mock[ReferenceStoreDao]
    mockWriter = mock[DataFrameV2Writer]
    annotationJobParameter = new AnnotationImportJobParameters(
      jobName = testJobName,
      databaseName = testDatabaseName,
      tableName = testTableName,
      tablePath = testTablePath,
      tableFormat = TableFormat.withName(testTableFormat),
      jobId = testJobId,
      inputPath = testVCFFile,
      referenceArn = testReferenceArn,
      runLeftNormalization = testRunLeftNormalization.toBoolean,
      storeFormat = StoreFormat.VCF,
      storeOptions = "",
      formatOptions = "",
      annotationFields = testAnnotationFields,
      tableSortKeys = Nil)
    super.beforeEach()
  }

  test("Test running annotation vcf import without dropping columns") {
    val expected = createTestVCFDataFrame(spark)
    val annotationJob = new AnnotationVCFJob(createTestComponent(annotationJobParameter))
    val data = annotationJob.run(annotationJobParameter)
    assertResult(expected.columns.toSet)(data.columns.toSet)
    assertResult(2)(data.count())
    expected.columns.toList.map { colName =>
      checkAnswer(expected.select(colName), data.select(colName))
    }
    assertResult(2)(data.filter(col("qual").isNotNull).count())
    assertResult(2)(data.filter(col("filters").isNotNull).count())
  }

  test("Dropping Qual") {

    val params = annotationJobParameter.copy(formatOptions =
      """{"vcfOptions": {"ignoreFilterField": true, "ignoreQualField": false}}""")
    val annotationJob = new AnnotationVCFJob(createTestComponent(params))
    val data = annotationJob.run(params)
    assertResult(2)(data.filter(col("qual").isNotNull).count())
    assertResult(0)(data.filter(col("filters").isNotNull).count())
  }

  test("Dropping Qual and Filter") {

    val params = annotationJobParameter.copy(formatOptions =
      """{"vcfOptions": {"ignoreFilterField": true, "ignoreQualField": true}}""")
    val annotationJob = new AnnotationVCFJob(createTestComponent(params))
    val data = annotationJob.run(params)
    assertResult(0)(data.filter(col("qual").isNotNull).count())
    assertResult(0)(data.filter(col("filters").isNotNull).count())
  }

  test("Dropping Filter") {

    val params = annotationJobParameter.copy(formatOptions =
      """{"vcfOptions": {"ignoreFilterField": true, "ignoreQualField": false}}""")
    val annotationJob = new AnnotationVCFJob(createTestComponent(params))
    val data = annotationJob.run(params)
    assertResult(2)(data.filter(col("qual").isNotNull).count())
    assertResult(0)(data.filter(col("filters").isNotNull).count())
  }
}
