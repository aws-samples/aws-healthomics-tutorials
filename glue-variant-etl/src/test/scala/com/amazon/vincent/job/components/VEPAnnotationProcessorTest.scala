// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components

import com.amazon.vincent.job.VincentTestSuite
import com.amazon.vincent.job.components.processors.VEPAnnotationProcessor
import com.amazon.vincent.job.models.Schema.AnnotationsFieldStruct
import com.amazon.vincent.job.models.exceptions.VincentUserException
import com.amazon.vincent.job.models.vep.{ExtraField, VepDefaultField, VepEntry, VepField}
import com.amazon.vincent.job.models.{AnnotationFields, TableFormat, VariantImportJobParameters}
import org.apache.spark.SparkConf
import org.apache.spark.sql.functions.col
import org.apache.spark.sql.test.SharedSparkSession
import org.apache.spark.sql.types.{MapType, StringType, StructField, StructType}
import org.apache.spark.sql.{QueryTest, Row}
import org.junit.runner.RunWith
import org.scalatest.BeforeAndAfterEach
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class VEPAnnotationProcessorTest
    extends QueryTest
    with SharedSparkSession
    with VincentTestSuite
    with BeforeAndAfterEach {

  import testImplicits._

  override def sparkConf: SparkConf = {
    super.sparkConf.set("spark.hadoop.io.compression.codecs", "io.projectglow.sql.util.BGZFCodec")
  }

  private def generateTestInfoStr(infoId: String): String = {
    s"""##INFO=<ID=$infoId,Number=.,Type=String,Description="Consequence annotations from Ensembl VEP. Format: Allele|Consequence|IMPACT">"""
  }

  private val testInfoStr = generateTestInfoStr("CSQ")

  private val testVepFieldsOrder =
    Some(
      Array(
        VepDefaultField.Allele,
        VepDefaultField.Consequence,
        VepDefaultField.Impact,
        VepDefaultField.Symbol,
        ExtraField("transcription_factors")))

  var params: VariantImportJobParameters = _

  override def beforeEach(): Unit = {
    super.beforeEach()
    params = new VariantImportJobParameters(
      jobName = testJobName,
      databaseName = testDatabaseName,
      tableName = testTableName,
      tablePath = testTablePath,
      tableFormat = TableFormat.ICEBERG_1,
      jobId = testJobId,
      inputPath = testVCFFile,
      referenceArn = testReferenceArn,
      runLeftNormalization = testRunLeftNormalization.toBoolean,
      annotationFields = testAnnotationFields,
      tableSortKeys = Nil)
  }

  test("Can retrieve from vcf file") {
    val vepAnnotationProcessor = VEPAnnotationProcessor.apply(spark, params, testVincentLogger)
    assertResult(testVepFieldsOrder.get.seq)(vepAnnotationProcessor.vepOrder.get.seq)
  }

  test("Can retrieve from bgz file") {
    val parameter = params.copy(inputPath = "./src/test/resources/variants.vcf.bgz")
    val vepAnnotationProcessor = VEPAnnotationProcessor.apply(spark, parameter, testVincentLogger)
    assertResult(testVepFieldsOrder.get.seq)(vepAnnotationProcessor.vepOrder.get.seq)
  }

  test("Only return matching INFO field") {
    val parameter = params.copy(annotationFields = AnnotationFields(Some("VEP")))
    val vepAnnotationProcessor = VEPAnnotationProcessor.apply(spark, parameter, testVincentLogger)
    assertResult(None)(vepAnnotationProcessor.vepOrder)
  }

  test("can retrieve if vep tag is not CSQ") {
    withTempFile(
      prefix = "random",
      suffix = ".vcf",
      { (file, writer) =>
        {
          val infoStr = generateTestInfoStr("vep")
          writer.write(s"$infoStr")
          writer.flush()
          val parameter = params.copy(annotationFields = AnnotationFields(Some("vep")))
          val vepAnnotationProcessor =
            VEPAnnotationProcessor.apply(spark, parameter, testVincentLogger)
          assertResult(None)(vepAnnotationProcessor.vepOrder)
        }
      })
  }

  test("return an annotation column if there is no VEP field") {
    val df = spark.emptyDataFrame
    val annotation = new VEPAnnotationProcessor(None, testVincentLogger).process(df, params)
    assertResult(Seq("annotations"))(annotation.columns)
  }

  test("Duplicate INFO tag fails") {
    withTempFile(
      prefix = "random",
      suffix = ".vcf",
      { (file, writer) =>
        {
          val parameters = params.copy(inputPath = file.getPath)
          writer.write(s"$testInfoStr\n$testInfoStr")
          writer.flush()
          val caught = intercept[VincentUserException] {
            VEPAnnotationProcessor.apply(spark, parameters, testVincentLogger)
          }
          assertResult(caught.getMessage)(
            "Duplicate VEP INFO header with ID: CSQ found in header.")
        }
      })
  }

  test("Do not fail if AnnotationFields Vep is null") {
    val parameter = params.copy(annotationFields = AnnotationFields(None))
    val processor = VEPAnnotationProcessor.apply(spark, parameter, testVincentLogger)
    assert(processor.vepOrder.isEmpty)
  }

  test("UDF return empty array where is there is a failure") {

    val fields: Array[VepField] =
      Array(VepDefaultField.Allele, VepDefaultField.Symbol, VepDefaultField.Impact)
    // when there are less entry in the vep string than in the schema
    val invalidVepString = "T|TP53"
    val validVepString = "T|TP53|moderate"

    val df = Seq(invalidVepString, validVepString).toDF("data")

    val processor = new VEPAnnotationProcessor(Some(fields), testVincentLogger)
    val udf = processor.getUdf(fields)
    val transformed = df
      .withColumn("annotations", udf(col("data")))
      .select(col("annotations.vep"))
      .as[Array[VepEntry]]
      .collect()

    assertResult(List())(transformed(0).toList)
    assertResult(
      List(VepEntry(allele = Some("T"), symbol = Some("TP53"), impact = Some("moderate"))))(
      transformed(1).toList)
  }

  test("Process basic use case with default and extra fields") {
    val parameter = new VariantImportJobParameters(
      jobName = testJobName,
      databaseName = testDatabaseName,
      tableName = testTableName,
      tablePath = testTablePath,
      tableFormat = TableFormat.ICEBERG_1,
      jobId = testJobId,
      inputPath = testVCFFile,
      referenceArn = testReferenceArn,
      runLeftNormalization = testRunLeftNormalization.toBoolean,
      annotationFields = AnnotationFields(Some("CSQ")),
      tableSortKeys = Nil)

    val processor = new VEPAnnotationProcessor(
      Some(Array(VepDefaultField.Allele, VepDefaultField.Consequence, ExtraField("cancer_type"))),
      testVincentLogger)

    val vepString =
      """T|intron_variant&non_coding_transcript_variant|stage4,A|intron_variant|"""

    val attributes = Map("CSQ" -> vepString)
    val annotation = Seq(attributes).toDF("attributes")

    val firstVepEntry = Row(
      "T",
      List("intron_variant", "non_coding_transcript_variant"),
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
      null,
      null,
      Map("cancer_type" -> "stage4"))

    val secondEntry = Row(
      "A",
      List("intron_variant"),
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
      null,
      null,
      Map("cancer_type" -> ""))

    val expected = Row(attributes, Row(Array(firstVepEntry, secondEntry)))

    val processed = processor.process(annotation, parameter)

    val df = spark.createDataFrame(
      spark.sparkContext.parallelize(expected :: Nil),
      StructType(
        Seq(
          StructField(
            "attributes",
            MapType(StringType, StringType, valueContainsNull = true),
            nullable = true),
          AnnotationsFieldStruct)))
    checkAnswer(df, processed)
  }

}
