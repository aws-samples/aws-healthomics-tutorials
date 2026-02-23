// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

import com.amazon.vincent.job.VincentTestSuite
import com.amazon.vincent.job.models.exceptions.VincentInternalException
import org.junit.runner.RunWith
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class AnnotationFieldsTest extends AnyFunSuite with VincentTestSuite {

  test("AnnotationFields.fromJsonString parses correctly") {
    assertResult(None)(AnnotationFields.fromJsonString("").vep)
    assertResult(None)(AnnotationFields.fromJsonString(" ").vep)
    assertResult(None)(AnnotationFields.fromJsonString("{}").vep)
    assertResult(None)(AnnotationFields.fromJsonString("{}").vep)
    assertResult(None)(AnnotationFields.fromJsonString("""{"NotVep": "NotVep"}""").vep)
    assertResult(None)(AnnotationFields.fromJsonString("""{"VEP": ""}""").vep)
    assertResult(None)(AnnotationFields.fromJsonString("""{"VEP": "     "}""").vep)
    assertResult(Some("csq"))(AnnotationFields.fromJsonString("""{"VEP": "csq"}""").vep)
  }

  test("Vincent Internal Exception is raised when the annotation field cannot parsed") {
    val caught = intercept[VincentInternalException] {
      AnnotationFields.fromJsonString("""{"VEP": true}""")
    }
    assert(
      caught.getMessage.startsWith(
        "Failed to parse Annotation fields parameter: {\"VEP\": true}."))
  }
}
