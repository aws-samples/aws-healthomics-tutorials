// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

import com.amazon.vincent.job.annotation.FormatOptionsJsonProtocol._
import com.amazon.vincent.job.annotation.{AnnotationStoreOptions, FormatOptions, TSVImportOptions}
import org.junit.runner.RunWith
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner
import spray.json._

@RunWith(classOf[JUnitRunner])
class TSVOptionsTest extends AnyFunSuite {

  val reference = "ref"
  val formatToHeader = Map("CHR" -> "CHR")
  val headers = List("CHR")
  val readOptions = Map("headers" -> "true")
  val skipLeftNorm = true

  private def decodeTsvOptions(jsonString: String): TSVImportOptions = {
    val jsonAst = jsonString.parseJson
    jsonAst.convertTo[FormatOptions].tsvOptions.get
  }

  private def decodeStoreOptions(jsonString: String): AnnotationStoreOptions = {
    val jsonAst = jsonString.parseJson
    jsonAst.convertTo[AnnotationStoreOptions]
  }

  test("TSVOptions accepts and process optional and ignore unused parameters") {
    val jsonString =
      s"""
        |{
        |  "tsvOptions" : {
        |    "readOptions" : {
        |      "quoteAll": false
        |     },
        |    "unused": "unused value"
        |  }
        |}
        |""".stripMargin
    val tsvOptions = decodeTsvOptions(jsonString)
    // bool are converted to string for readOptions
    assert(tsvOptions.readOptions.get("quoteAll") === "false")
  }

  test("TsvStoreOptions are parse correctly") {
    val storeOptions =
      s"""
         |{
         |  "tsvStoreOptions": {
         |    "annotationType": "CHR_POS",
         |    "schema": "[{\\\"chrom\\\": \\\"STRING\\\"}, {\\\"position\\\": \\\"LONG\\\"}]",
         |    "formatToHeader": {
         |      "CHR": "chrom",
         |      "POS": "position"
         |    }
         |  }
         |}
         |""".stripMargin
    val annotationStoreOpts = decodeStoreOptions(storeOptions)
    val tsvStoreOptions = annotationStoreOpts.tsvStoreOptions.get
    assert(tsvStoreOptions.annotationType.get === AnnotationType.ChrPos.name)
    assert(tsvStoreOptions.formatToHeader.get === Map("CHR" -> "chrom", "POS" -> "position"))
    assert(tsvStoreOptions.schema.get === "[{\"chrom\": \"STRING\"}, {\"position\": \"LONG\"}]")

    val tsvSchemaList = tsvStoreOptions.schema.get.parseJson.convertTo[List[Map[String, String]]]
    assert(tsvSchemaList == List(Map("chrom" -> "STRING"), Map("position" -> "LONG")))
  }

}
