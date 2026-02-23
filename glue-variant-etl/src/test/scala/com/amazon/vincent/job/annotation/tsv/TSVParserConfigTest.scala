// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

import org.junit.runner.RunWith
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class TSVParserConfigTest extends AnyFunSuite {

  val inputFile = "s3://MOCK"
  val annotationType = "CHR_POS_REF_ALT"
  val reference = "src/test/resources/references/test.fasta"
  val formatToHeaderJson =
    "{\"CHR\": \"chromosome\", \"POS\": \"start\", \"REF\": \"ref_alleles\", \"ALT\": \"alt\"}"

  val schemaString: String =
    "[{\\\"chromosome\\\": \\\"STRING\\\"}, {\\\"position\\\": \\\"LONG\\\"}, {\\\"ref_alleles\\\": \\\"STRING\\\"}, {\\\"alt\\\": \\\"STRING\\\"}]"

  test(
    "TSVParserArgParse throws error if FORMAT_TO_HEADER is missing for structured annotation type") {

    val formatOptionsString = "{}"

    val storeOptionsString =
      s"""
         |{
         |  "tsvStoreOptions": {
         |     "annotationType": "$annotationType",
         |     "schema": "$schemaString"
         |  }
         |}
         |""".stripMargin

    val caught = intercept[java.util.NoSuchElementException] {
      TSVParserConfig.parseFromGlueArgs(
        inputFile,
        formatOptionsString,
        storeOptionsString,
        Some(reference))
    }
  }

  test("TSVParserArgParse throws error if are missing keys in FORMAT_TO_HEADER") {
    val formatOptionsString = "{}"
    val storeOptionsString =
      s"""
         |{
         | "tsvOptions": {
         |  "annotationType": "$annotationType",
         |   "schema": "$schemaString",
         |   "formatToHeader": {"CHR": "A"}
         | }
         |}
         |""".stripMargin

    val caught = intercept[java.util.NoSuchElementException] {
      TSVParserConfig.parseFromGlueArgs(
        inputFile,
        formatOptionsString,
        storeOptionsString,
        reference = Some(reference))
    }
  }

  test("TSVParserConfig parse from GlueArgs") {
    val formatOptionsString = "{}"
    val storeOptionsString =
      s"""
         |{
         |  "tsvStoreOptions": {
         |     "annotationType": "$annotationType",
         |     "schema": "$schemaString",
         |     "formatToHeader": $formatToHeaderJson
         |  }
         |}
         |""".stripMargin

    val config =
      TSVParserConfig.parseFromGlueArgs(
        inputFile = inputFile,
        formatOptionsString = formatOptionsString,
        storeOptionsString = storeOptionsString,
        Some(reference))

    assert(config.inputFile == "s3://MOCK")
    assert(
      config.sparkOptions === Map(
        "header" -> "true",
        "delimiter" -> "\t",
        "inferSchema" -> "true"))
    assert(config.annotationType === AnnotationType(annotationType))
    assert(config.schema === "chromosome STRING ,position LONG ,ref_alleles STRING ,alt STRING")
    assert(
      config.formatHeader.get === FormatHeader(
        "chromosome",
        "start",
        "end",
        "ref_alleles",
        "alt"))
    assert(config.sparkURL === None)
    assert(config.out === None)
    assert(config.reference.get === Reference(reference))
    assert(config.runLeftNormalization === false)
  }

  test("TSVParserConfig throws error when reference is None and runLeftNormalization is true") {
    val formatOptionsString = "{}"
    val storeOptionsString =
      s"""
         |{
         |  "tsvStoreOptions": {
         |     "annotationType": "$annotationType",
         |     "schema": "$schemaString",
         |     "formatToHeader": $formatToHeaderJson
         |  }
         |}
         |""".stripMargin

    intercept[RuntimeException] {
      TSVParserConfig.parseFromGlueArgs(
        inputFile = inputFile,
        formatOptionsString = formatOptionsString,
        storeOptionsString = storeOptionsString,
        reference = None,
        runLeftNormalization = true)
    }
  }
}
