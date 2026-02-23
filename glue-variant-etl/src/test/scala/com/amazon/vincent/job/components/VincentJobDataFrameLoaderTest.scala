// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components

import com.amazon.vincent.job.VincentTestSuite
import com.amazon.vincent.job.models.exceptions.VincentUserException
import org.apache.spark.sql.test.SharedSparkSession
import org.apache.spark.sql.{QueryTest, Row, SparkSession}
import org.junit.runner.RunWith
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class VincentJobDataFrameLoaderTest
    extends QueryTest
    with VincentTestSuite
    with SharedSparkSession {

  test("Test VariantJobDataFrameLoader can load vcf files with non flatten info") {
    val df = new VCFDataFrameLoader().load(spark, testVCFFile)
    val expectCols = Array(
      "contigName",
      "start",
      "end",
      "names",
      "referenceAllele",
      "alternateAlleles",
      "qual",
      "filters",
      "splitFromMultiAllelic",
      "attributes",
      "genotypes")
    assertResult(expectCols)(df.columns)
    checkAnswer(
      df.select("attributes"),
      Row(Map("CSQ" -> testInfoCSQValue, "VARID" -> "ATXN7")) :: Nil)
  }

  test("Test missing version") {
    val df = intercept[VincentUserException] {
      new VCFDataFrameLoader().load(spark, "./src/test/resources/data/missing_version.vcf")
    }
    assertResult(df.getMessage) {
      "VCF header does not contain VCF version."
    }
  }

  test("Test insufficient header columns") {
    val df = intercept[VincentUserException] {
      new VCFDataFrameLoader()
        .load(spark, "./src/test/resources/data/insufficient_header_columns.vcf")
    }
    assertResult(df.getMessage) {
      "VCF header does not have sufficient number of required fields. Please ensure required header fields are present as per specification."
    }
  }

  test("Test unknown header column") {
    val df = intercept[VincentUserException] {
      new VCFDataFrameLoader().load(spark, "./src/test/resources/data/unknown_header_column.vcf")
    }
    assertResult(df.getMessage) {
      "VCF header fields are not in order as defined by specification. Please ensure fields are as per specification."
    }
  }

  test("Test unsupported version") {
    val df = intercept[VincentUserException] {
      new VCFDataFrameLoader().load(spark, "./src/test/resources/data/unsupported_version.vcf")
    }
    assertResult(df.getMessage) {
      "Unsupported VCF version."
    }
  }

  test("Test missing header") {
    val df = intercept[VincentUserException] {
      new VCFDataFrameLoader()
        .load(spark, "./src/test/resources/data/variants_twosamples_missingHeader.vcf")
    }
    assertResult(df.getMessage) {
      "VCF header does not contain required CHROM header line (starting with one #)."
    }
  }

  test("Test header not tab delimited") {
    val df = intercept[VincentUserException] {
      new VCFDataFrameLoader()
        .load(spark, "./src/test/resources/data/variants_singlesample_headernottabdelimeted.vcf")
    }
    assertResult(df.getMessage) {
      "VCF header contains an illegal field name. Please ensure fields are as per specification."
    }
  }

  test("Test header sample null") {
    val df = intercept[VincentUserException] {
      new VCFDataFrameLoader()
        .load(spark, "./src/test/resources/data/header_sample_null.vcf")
    }
    assertResult(df.getMessage) {
      "Invalid VCF Header: field must not be null."
    }
  }

  test("Test invalid Type in header") {
    val df = intercept[VincentUserException] {
      new VCFDataFrameLoader()
        .load(spark, "./src/test/resources/data/Invalid_type_header.vcf")
    }
    assertResult(df.getMessage) {
      "VCF header contains an invalid value for Type. Please ensure header is as per specification."
    }
  }

  test("Test header invalid count number") {
    val df = intercept[VincentUserException] {
      new VCFDataFrameLoader()
        .load(spark, "./src/test/resources/data/Invalid_count_number.vcf")
    }
    assertResult(df.getMessage) {
      "VCF header contains an invalid count for NUMBER, with fixed count the number should be 1 or higher."
    }
  }

  test("Test malformed header") {
    val df = intercept[VincentUserException] {
      new VCFDataFrameLoader()
        .load(spark, "./src/test/resources/data/malformed_header_no_id.vcf")
    }
    assertResult(df.getMessage) {
      "VCF header is malformed. Please ensure header is as per specification."
    }
  }
}
