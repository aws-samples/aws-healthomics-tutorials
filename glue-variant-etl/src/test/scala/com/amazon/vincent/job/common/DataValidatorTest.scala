// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

import com.amazon.vincent.job.VincentTestSuite
import com.amazon.vincent.job.common.DataValidationStatuses.{FAIL_PARTIAL_WRITE, PASS}
import com.amazon.vincent.job.models.Schema
import com.amazon.vincent.job.models.exceptions.{DataValidationException, VincentUserException}
import com.amazonaws.services.glue.GlueContext
import org.apache.spark.sql.{DataFrame, QueryTest, Row, SparkSession}
import org.apache.spark.sql.test.SharedSparkSession
import org.apache.spark.sql.types.{LongType, StructField, StructType}
import org.junit.runner.RunWith
import org.mockito.MockitoSugar.{mock, when}
import org.scalatest.BeforeAndAfterEach
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class DataValidatorTest
    extends QueryTest
    with VincentTestSuite
    with SharedSparkSession
    with BeforeAndAfterEach {

  val tableLocation: String = "TEST_TABLE"
  val importJobId: String = testJobId
  val expectedSqlString: String =
    s"SELECT COUNT (*) FROM $tableLocation WHERE importjobid = '$importJobId'"
  val countSchema: StructType =
    StructType(Array(StructField("COUNT(1)", LongType, nullable = true)))

  var mockGlueContext: GlueContext = _
  var mockSparkSession: SparkSession = _

  override def beforeEach(): Unit = {
    mockGlueContext = mock[GlueContext]
    mockSparkSession = mock[SparkSession]
    when(mockGlueContext.getSparkSession).thenReturn(mockSparkSession)
    super.beforeEach()
  }

  test("When expected rows equals actual, validation passed") {
    val dfFromReadingVCF: DataFrame =
      createTestVCFDataFrame(
        spark = this.spark,
        expectedRows = testVCFFileRows,
        schema = Schema.VariantSchemaWithInfo)

    val sqlCountRows = List(Row(2L))
    val dfFromReadingGlueTable: DataFrame =
      this.spark
        .createDataFrame(this.spark.sparkContext.parallelize(sqlCountRows), countSchema)

    when(mockSparkSession.sql(expectedSqlString)).thenReturn(dfFromReadingGlueTable)

    val result = DataValidator.check(
      dfFromReadingVCF,
      glueContext = mockGlueContext,
      tableLocation = tableLocation,
      importJobId = importJobId)
    assertResult(PASS)(result)
  }

  test("When expected rows does not equal actual, alert partial write") {
    val dfFromReadingVCF: DataFrame =
      createTestVCFDataFrame(
        spark = this.spark,
        expectedRows = testVCFFileRows,
        schema = Schema.VariantSchemaWithInfo)

    val sqlCountRows = List(Row(1L))
    val dfFromReadingGlueTable: DataFrame =
      this.spark
        .createDataFrame(this.spark.sparkContext.parallelize(sqlCountRows), countSchema)

    when(mockSparkSession.sql(expectedSqlString)).thenReturn(dfFromReadingGlueTable)

    val result = DataValidator.check(
      dfFromReadingVCF,
      glueContext = mockGlueContext,
      tableLocation = tableLocation,
      importJobId = importJobId)
    assertResult(FAIL_PARTIAL_WRITE)(result)
  }

  test("When file has non-zero rows, but zero rows written, throw internal-only exception") {
    val dfFromReadingVCF: DataFrame =
      createTestVCFDataFrame(
        spark = this.spark,
        expectedRows = testVCFFileRows,
        schema = Schema.VariantSchemaWithInfo)

    val sqlCountRows = List(Row(0L))
    val dfFromReadingGlueTable: DataFrame =
      this.spark
        .createDataFrame(this.spark.sparkContext.parallelize(sqlCountRows), countSchema)

    when(mockSparkSession.sql(expectedSqlString)).thenReturn(dfFromReadingGlueTable)

    val caught =
      intercept[DataValidationException](
        DataValidator.check(
          dfFromReadingVCF,
          glueContext = mockGlueContext,
          tableLocation = tableLocation,
          importJobId = importJobId))
    assert(caught.getMessage.nonEmpty)
  }

  test("When file has zero rows, throw customer-facing exception") {
    val dfFromReadingVCF: DataFrame =
      createTestVCFDataFrame(
        spark = this.spark,
        expectedRows = Seq(),
        schema = Schema.VariantSchemaWithInfo)

    val sqlCountRows = List(Row(0L))
    val dfFromReadingGlueTable: DataFrame =
      this.spark
        .createDataFrame(this.spark.sparkContext.parallelize(sqlCountRows), countSchema)

    when(mockSparkSession.sql(expectedSqlString)).thenReturn(dfFromReadingGlueTable)

    val caught =
      intercept[VincentUserException](
        DataValidator.check(
          dfFromReadingVCF,
          glueContext = mockGlueContext,
          tableLocation = tableLocation,
          importJobId = importJobId))
    assert(caught.getMessage.nonEmpty)
  }
}
