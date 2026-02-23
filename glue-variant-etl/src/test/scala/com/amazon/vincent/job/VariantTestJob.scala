// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job

import com.amazon.vincent.job.common.ReferenceStoreDao
import com.amazon.vincent.job.components.processors.{
  AddImportJobIdProcessor,
  ExplodeGenotypeProcessor,
  MissingAndAdditionalFieldsProcessor,
  VCFLeftNormalizationProcessor,
  VEPAnnotationProcessor
}
import com.amazon.vincent.job.components.{
  DataFrameV2Writer,
  VCFDataFrameLoader,
  VariantJobComponent
}
import com.amazon.vincent.job.models.vep.VepEntry
import com.amazon.vincent.job.models.{
  AnnotationFields,
  Schema,
  TableFormat,
  VariantImportJobParameters
}
import org.apache.spark.SparkConf
import org.apache.spark.sql.functions.col
import org.apache.spark.sql.test.SharedSparkSession
import org.apache.spark.sql.{QueryTest, Row}
import org.junit.runner.RunWith
import org.mockito.MockitoSugar.mock
import org.scalatestplus.junit.JUnitRunner

import scala.collection.mutable.ArrayBuffer

@RunWith(classOf[JUnitRunner])
class VariantTestJob extends QueryTest with SharedSparkSession with VincentTestSuite {

  import testImplicits._

  override def sparkConf: SparkConf = {
    super.sparkConf.set("spark.hadoop.io.compression.codecs", "io.projectglow.sql.util.BGZFCodec")
  }

  val mockReferenceStoreDao = mock[ReferenceStoreDao]
  val mockWriter = mock[DataFrameV2Writer]

  private val testParameter = new VariantImportJobParameters(
    jobName = testJobName,
    databaseName = testDatabaseName,
    tableName = testTableName,
    tablePath = testTablePath,
    tableFormat = TableFormat.withName(testTableFormat),
    jobId = testJobId,
    inputPath = testVCFFile,
    referenceArn = testReferenceArn,
    runLeftNormalization = testRunLeftNormalization.toBoolean,
    annotationFields = testAnnotationFields,
    tableSortKeys = Nil)

  def createVariantJobComponent(parameter: VariantImportJobParameters): VariantJobComponent = {
    VariantJobComponent(
      spark,
      mockWriter,
      new VCFDataFrameLoader(),
      Seq(
        new VCFLeftNormalizationProcessor(mockReferenceStoreDao, testVincentLogger),
        new ExplodeGenotypeProcessor,
        VEPAnnotationProcessor(spark, parameter, testVincentLogger),
        new AddImportJobIdProcessor,
        new MissingAndAdditionalFieldsProcessor(testVincentLogger)),
      testVincentLogger)
  }

  test("Test Variant Job Start to End Without VEP Support") {
    val variantJobComponent = createVariantJobComponent(testParameter)
    val variantJob = new VariantJob(variantJobComponent)
    val data = variantJob.run(testParameter)

    val expected = createTestVCFDataFrame(spark)
    assertResult(expected.columns.toSet)(data.columns.toSet)
    assertResult(2)(data.count())
    expected.columns.toList.map { colName =>
      checkAnswer(expected.select(colName), data.select(colName))
    }
  }

  test("Test Variant Job Start to End With VEP Support") {
    val vepParameter = testParameter.copy(tableFormat = TableFormat.ICEBERG_1)
    val variantJobComponent = createVariantJobComponent(vepParameter)

    val variantJob = new VariantJob(variantJobComponent)
    val data = variantJob.run(vepParameter)

    val annotationField = List(
      Row(
        "T",
        List("intron_variant", "non_coding_transcript_variant"),
        "MODIFIER",
        "ANKEF1",
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        Map("transcription_factors" -> "")),
      Row(
        "T",
        List("downstream_gene_variant"),
        "MODIFIER",
        "SNAP25-AS1",
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        Map("transcription_factors" -> "TFA")))

    val vcfRowWithNullAnnotation = Seq(
      Row(
        testJobId,
        "chr3",
        63912683,
        63912684,
        null,
        "G",
        List("T"),
        10.0,
        List("PASS"),
        false,
        Map("CSQ" -> testInfoCSQValue, "VARID" -> "ATXN7"),
        false,
        ArrayBuffer(0, 0),
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        "HG0001",
        null,
        Row(annotationField)),
      Row(
        testJobId,
        "chr3",
        63912683,
        63912684,
        null,
        "G",
        List("T"),
        10.0,
        List("PASS"),
        false,
        Map("CSQ" -> testInfoCSQValue, "VARID" -> "ATXN7"),
        false,
        List(1, 0),
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        "HG0002",
        null,
        Row(annotationField)))

    val expected = spark.createDataFrame(
      spark.sparkContext.parallelize(vcfRowWithNullAnnotation),
      Schema.VariantSchemaWithInfoAndAnno)

    assertResult(2)(data.count())
    expected.columns.toList.map { colName =>
      checkAnswer(expected.select(colName), data.select(colName))
    }
  }

  test("Test Variant Job with that supports VEP parsing but does not contains vep entries") {
    val vepParameter = testParameter.copy(
      tableFormat = TableFormat.ICEBERG_1,
      inputPath = "./src/test/resources/variants.no_vep.vcf")
    val variantJobComponent = createVariantJobComponent(vepParameter)
    val variantJob = new VariantJob(variantJobComponent)
    val data = variantJob.run(vepParameter)
    assertResult(4)(data.count())

    val rows = data.select(col("annotations.vep")).collect().toList

    assertResult(rows)(Seq.fill(4)(Row(null)))

  }

  test("Test Variant Job Start to End With Data from Gnomad VCF") {
    val vepParameter = testParameter.copy(
      tableFormat = TableFormat.ICEBERG_1,
      annotationFields = AnnotationFields(vep = Some("vep")),
      inputPath = "./src/test/resources/variants.gnomad.vcf")
    val variantJobComponent = createVariantJobComponent(vepParameter)
    val variantJob = new VariantJob(variantJobComponent)
    val data = variantJob.run(vepParameter)
    assertResult(2)(data.count())
    val row = data.select(col("annotations.vep")).as[Array[VepEntry]].collect()

    assertResult(row.head.length)(7)
    assertResult(row.head.map { _.symbol.get })(
      List(
        "FP565260.5",
        "GATD3B",
        "GATD3B",
        "CH507-9B2.8",
        "CH507-9B2.8",
        "LOC107987292",
        "CH507-9B2.8"))
    // unable to parse Lof_info because of comma in the value, return empty vep array
    assertResult(row.last)(Array())
  }

  test("Test Variant Job Start to End that has CSQ tag but is not a vep annotation") {
    val vepParameter = testParameter.copy(
      tableFormat = TableFormat.ICEBERG_1,
      annotationFields = AnnotationFields(vep = Some("CSQ")),
      inputPath = "./src/test/resources/variants.has_csq_no_schema.vcf")
    val variantJobComponent = createVariantJobComponent(vepParameter)
    val variantJob = new VariantJob(variantJobComponent)
    val data = variantJob.run(vepParameter)
    assertResult(4)(data.count())
    val rows = data.select(col("annotations.vep")).collect().toList
    // unable to parse Lof_info because of comma in the value, return empty vep array
    assertResult(rows)(Seq.fill(4)(Row(null)))
  }

  test("Test Variant Job Start to End user provide vep tag but is not a vep annotation") {
    val vepParameter = testParameter.copy(
      tableFormat = TableFormat.ICEBERG_1,
      annotationFields = AnnotationFields(vep = Some("vep")),
      inputPath = "./src/test/resources/variants.not_csq_no_schema.vcf")
    val variantJobComponent = createVariantJobComponent(vepParameter)
    val variantJob = new VariantJob(variantJobComponent)
    val data = variantJob.run(vepParameter)
    assertResult(4)(data.count())
    val rows = data.select(col("annotations.vep")).collect().toList
    // unable to parse Lof_info because of comma in the value, return empty vep array
    assertResult(rows)(Seq.fill(4)(Row(null)))
  }

  test("Test Variant Job with vcf containing rows with missing vep annotation") {
    val vepParameter = testParameter.copy(
      tableFormat = TableFormat.ICEBERG_1,
      annotationFields = AnnotationFields(vep = Some("vep")),
      inputPath = "./src/test/resources/variants.gnomad.with.missing.vep.rows.vcf")
    val variantJobComponent = createVariantJobComponent(vepParameter)
    val variantJob = new VariantJob(variantJobComponent)
    val data = variantJob.run(vepParameter)
    val rows = data.select(col("annotations.vep")).as[Array[VepEntry]].collect()
    assertResult(rows.head.length)(7)
    assertResult(rows.head.map { _.symbol.get })(
      List(
        "FP565260.5",
        "GATD3B",
        "GATD3B",
        "CH507-9B2.8",
        "CH507-9B2.8",
        "LOC107987292",
        "CH507-9B2.8"))

    // unable to parse rows that does not contain vep id in info column
    assertResult(rows.last)(Array())

  }
}
